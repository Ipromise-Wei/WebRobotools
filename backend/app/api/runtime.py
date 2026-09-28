import base64
import binascii
import math
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
import yaml

from app.core.dependencies import get_remote_runtime
from app.core.remote_runtime import RemoteRuntimeError, RemoteRuntimeManager
from app.models.runtime import (
    MapImportRequest,
    MapLibrary,
    MapSaveRequest,
    RuntimeActionResponse,
    RuntimeLog,
    RuntimeStatus,
)


router = APIRouter()


async def clear_live_map_cache(request: Request) -> None:
    """Discard the Web copy after a remote SLAM session is stopped/replaced."""
    adapter = request.app.state.ros2_adapter
    if adapter is None:
        return
    snapshot = adapter.clear_map_cache()
    await request.app.state.map_manager.replace(snapshot)


def failure(exc: RemoteRuntimeError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


def bad_map(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def decode_imported_map(payload: MapImportRequest) -> tuple[bytes, bytes]:
    try:
        yaml_input = base64.b64decode(payload.yaml_base64, validate=True)
        pgm = base64.b64decode(payload.pgm_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise bad_map("地图文件编码无效") from exc
    if len(yaml_input) > 1_000_000 or len(pgm) > 24_000_000:
        raise bad_map("地图文件过大")
    if not (pgm.startswith(b"P2") or pgm.startswith(b"P5")):
        raise bad_map("仅支持 ROS 地图使用的 PGM 图像")
    try:
        raw = yaml.safe_load(yaml_input.decode("utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("YAML 根节点必须是对象")
        resolution = float(raw["resolution"])
        origin = raw["origin"]
        if not math.isfinite(resolution) or resolution <= 0 or not isinstance(origin, list) or len(origin) != 3:
            raise ValueError("地图分辨率或原点无效")
        origin_values = [float(value) for value in origin]
        if not all(math.isfinite(value) for value in origin_values):
            raise ValueError("地图原点无效")
        normalized = {
            "image": f"{payload.name}.pgm",
            "mode": str(raw.get("mode", "trinary")),
            "resolution": resolution,
            "origin": origin_values,
            "negate": int(raw.get("negate", 0)),
            "occupied_thresh": float(raw.get("occupied_thresh", 0.65)),
            "free_thresh": float(raw.get("free_thresh", 0.25)),
        }
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise bad_map("地图 YAML 必须是有效的 ROS map_server 地图描述文件") from exc
    return yaml.safe_dump(normalized, allow_unicode=True, sort_keys=False).encode("utf-8"), pgm


@router.get("/status", response_model=RuntimeStatus)
async def status(
    runtime: Annotated[RemoteRuntimeManager, Depends(get_remote_runtime)],
) -> RuntimeStatus:
    return await runtime.status()


@router.post("/tasks/{task_id}/start", response_model=RuntimeActionResponse)
async def start_task(
    task_id: str,
    runtime: Annotated[RemoteRuntimeManager, Depends(get_remote_runtime)],
) -> RuntimeActionResponse:
    try:
        result = await runtime.task_action(task_id, "start")
    except RemoteRuntimeError as exc:
        raise failure(exc) from exc
    return RuntimeActionResponse(success=True, status=result)


@router.post("/start", response_model=RuntimeActionResponse)
async def start(
    runtime: Annotated[RemoteRuntimeManager, Depends(get_remote_runtime)],
) -> RuntimeActionResponse:
    try:
        result = await runtime.start()
    except RemoteRuntimeError as exc:
        raise failure(exc) from exc
    return RuntimeActionResponse(success=True, status=result)


@router.post("/basic/start", response_model=RuntimeActionResponse)
async def start_basic_modules(
    runtime: Annotated[RemoteRuntimeManager, Depends(get_remote_runtime)],
) -> RuntimeActionResponse:
    """Start only the six shared ROS2 base modules, in dependency order."""
    try:
        result = await runtime.start_profile("basic_modules")
    except RemoteRuntimeError as exc:
        raise failure(exc) from exc
    return RuntimeActionResponse(success=True, status=result)


@router.post("/mapping/manual/start", response_model=RuntimeActionResponse)
async def start_manual_mapping(
    runtime: Annotated[RemoteRuntimeManager, Depends(get_remote_runtime)],
) -> RuntimeActionResponse:
    try:
        result = await runtime.start_mapping_profile("manual_mapping")
    except RemoteRuntimeError as exc:
        raise failure(exc) from exc
    return RuntimeActionResponse(success=True, status=result)


@router.post("/mapping/automatic/start", response_model=RuntimeActionResponse)
async def start_automatic_mapping(
    runtime: Annotated[RemoteRuntimeManager, Depends(get_remote_runtime)],
) -> RuntimeActionResponse:
    try:
        result = await runtime.start_mapping_profile("automatic_mapping")
    except RemoteRuntimeError as exc:
        raise failure(exc) from exc
    return RuntimeActionResponse(success=True, status=result)


@router.post("/mapping/stop", response_model=RuntimeActionResponse)
async def stop_mapping(
    request: Request,
    runtime: Annotated[RemoteRuntimeManager, Depends(get_remote_runtime)],
) -> RuntimeActionResponse:
    try:
        result = await runtime.stop_mapping()
        await clear_live_map_cache(request)
    except RemoteRuntimeError as exc:
        raise failure(exc) from exc
    return RuntimeActionResponse(success=True, status=result)


@router.get("/maps", response_model=MapLibrary)
async def maps(
    runtime: Annotated[RemoteRuntimeManager, Depends(get_remote_runtime)],
) -> MapLibrary:
    try:
        return MapLibrary(maps=await runtime.list_maps())
    except RemoteRuntimeError as exc:
        raise failure(exc) from exc


@router.post("/maps/save", response_model=MapLibrary)
async def save_map(
    payload: MapSaveRequest,
    runtime: Annotated[RemoteRuntimeManager, Depends(get_remote_runtime)],
) -> MapLibrary:
    try:
        return MapLibrary(maps=await runtime.save_map(payload.name))
    except RemoteRuntimeError as exc:
        raise failure(exc) from exc


@router.post("/maps/import", response_model=MapLibrary)
async def import_map(
    payload: MapImportRequest,
    runtime: Annotated[RemoteRuntimeManager, Depends(get_remote_runtime)],
) -> MapLibrary:
    yaml_content, image_content = decode_imported_map(payload)
    try:
        return MapLibrary(maps=await runtime.import_map(payload.name, yaml_content, image_content))
    except RemoteRuntimeError as exc:
        raise failure(exc) from exc


@router.post("/stop", response_model=RuntimeActionResponse)
async def stop(
    request: Request,
    runtime: Annotated[RemoteRuntimeManager, Depends(get_remote_runtime)],
) -> RuntimeActionResponse:
    try:
        result = await runtime.stop()
        await clear_live_map_cache(request)
    except RemoteRuntimeError as exc:
        raise failure(exc) from exc
    return RuntimeActionResponse(success=True, status=result)


@router.post("/tasks/{task_id}/stop", response_model=RuntimeActionResponse)
async def stop_task(
    task_id: str,
    request: Request,
    runtime: Annotated[RemoteRuntimeManager, Depends(get_remote_runtime)],
) -> RuntimeActionResponse:
    try:
        result = await runtime.task_action(task_id, "stop")
        if task_id == "slam":
            await clear_live_map_cache(request)
    except RemoteRuntimeError as exc:
        raise failure(exc) from exc
    return RuntimeActionResponse(success=True, status=result)


@router.post("/tasks/{task_id}/restart", response_model=RuntimeActionResponse)
async def restart_task(
    task_id: str,
    runtime: Annotated[RemoteRuntimeManager, Depends(get_remote_runtime)],
) -> RuntimeActionResponse:
    try:
        result = await runtime.task_action(task_id, "restart")
    except RemoteRuntimeError as exc:
        raise failure(exc) from exc
    return RuntimeActionResponse(success=True, status=result)


@router.get("/logs", response_model=RuntimeLog)
async def logs(
    runtime: Annotated[RemoteRuntimeManager, Depends(get_remote_runtime)],
    lines: Annotated[int, Query(ge=1, le=500)] = 120,
) -> RuntimeLog:
    try:
        return RuntimeLog(lines=await runtime.logs(lines))
    except RemoteRuntimeError as exc:
        raise failure(exc) from exc
