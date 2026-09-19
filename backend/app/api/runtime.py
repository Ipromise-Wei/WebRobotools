from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.dependencies import get_remote_runtime
from app.core.remote_runtime import RemoteRuntimeError, RemoteRuntimeManager
from app.models.runtime import RuntimeActionResponse, RuntimeLog, RuntimeStatus


router = APIRouter()


def failure(exc: RemoteRuntimeError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


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


@router.post("/stop", response_model=RuntimeActionResponse)
async def stop(
    runtime: Annotated[RemoteRuntimeManager, Depends(get_remote_runtime)],
) -> RuntimeActionResponse:
    try:
        result = await runtime.stop()
    except RemoteRuntimeError as exc:
        raise failure(exc) from exc
    return RuntimeActionResponse(success=True, status=result)


@router.post("/tasks/{task_id}/stop", response_model=RuntimeActionResponse)
async def stop_task(
    task_id: str,
    runtime: Annotated[RemoteRuntimeManager, Depends(get_remote_runtime)],
) -> RuntimeActionResponse:
    try:
        result = await runtime.task_action(task_id, "stop")
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
