from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_map_manager
from app.core.map_manager import MapManager
from app.models.visualization import CameraStreamStatus, MapSnapshot, VisualizationConfig

router = APIRouter()


@router.get("/config", response_model=VisualizationConfig)
async def config(request: Request) -> VisualizationConfig:
    settings = request.app.state.settings
    adapter = request.app.state.ros2_adapter
    camera = request.app.state.realsense_stream
    camera_status = camera.status()
    camera_url = settings.visualization.camera_stream_url.strip()
    if not camera_url and camera_status.enabled:
        camera_url = "/api/visualization/camera/stream"
    return VisualizationConfig(
        camera_stream_url=camera_url,
        camera_enabled=bool(camera_url),
        camera_connected=(camera_status.connected if camera_status.enabled else bool(camera_url)),
        camera_serial=camera_status.serial,
        camera_error=camera_status.error,
        map_topic=settings.ros2.map_topic,
        plan_topic=settings.ros2.plan_topic,
        motion_commands_enabled=(
            settings.ros2.allow_motion_commands
            and adapter is not None
            and adapter.motion_commands_ready()
        ),
    )


@router.get("/camera/status", response_model=CameraStreamStatus)
async def camera_status(request: Request) -> CameraStreamStatus:
    return request.app.state.realsense_stream.status()


@router.get("/camera/stream")
async def camera_stream(request: Request) -> StreamingResponse:
    stream = request.app.state.realsense_stream
    if not stream.status().enabled:
        raise HTTPException(status_code=404, detail="RealSense 真机视频流未启用")
    return StreamingResponse(
        stream.mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@router.get("/map", response_model=MapSnapshot)
async def current_map(manager: Annotated[MapManager, Depends(get_map_manager)]) -> MapSnapshot:
    _, snapshot = await manager.snapshot()
    return snapshot
