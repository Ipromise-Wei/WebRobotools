from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.dependencies import get_map_manager
from app.core.map_manager import MapManager
from app.models.visualization import (
    CameraEnabledRequest,
    CameraStreamStatus,
    NavigationGoalRequest,
    NavigationStatus,
    VisualizationConfig,
)

router = APIRouter()


def _visualization_config(request: Request) -> VisualizationConfig:
    settings = request.app.state.settings
    adapter = request.app.state.ros2_adapter
    camera = request.app.state.realsense_stream
    camera_status = camera.status()
    camera_url = settings.visualization.camera_stream_url.strip()
    navigation_ready, navigation_reason = adapter.navigation_readiness() if adapter is not None else (False, "后端不是 ROS2 真机模式")
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
        navigation_ready=navigation_ready,
        navigation_reason=navigation_reason,
    )


@router.get("/config", response_model=VisualizationConfig)
async def config(request: Request) -> VisualizationConfig:
    return _visualization_config(request)


@router.post("/camera/enabled", response_model=VisualizationConfig)
async def set_camera_enabled(
    request: Request, payload: CameraEnabledRequest
) -> VisualizationConfig:
    if request.app.state.settings.visualization.camera_stream_url.strip():
        raise HTTPException(
            status_code=409,
            detail="外部视频流由服务端配置管理，不能在页面中动态启停",
        )
    await request.app.state.realsense_stream.set_enabled(payload.enabled)
    return _visualization_config(request)


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
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            # Disable reverse-proxy buffering; a monitoring stream must show
            # the newest frame instead of a buffered multipart response.
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/map")
async def current_map(manager: Annotated[MapManager, Depends(get_map_manager)]) -> JSONResponse:
    _, snapshot = await manager.transport_snapshot()
    return JSONResponse(snapshot)


@router.post("/map/cache/clear")
async def clear_map_cache(
    request: Request,
    manager: Annotated[MapManager, Depends(get_map_manager)],
) -> JSONResponse:
    adapter = request.app.state.ros2_adapter
    if adapter is None:
        raise HTTPException(status_code=423, detail="地图缓存清除仅适用于 ROS2 真机模式")
    snapshot = adapter.clear_map_cache()
    await manager.replace(snapshot)
    _, payload = await manager.transport_snapshot()
    return JSONResponse(payload)


@router.get("/navigation/status", response_model=NavigationStatus)
async def navigation_status(request: Request) -> NavigationStatus:
    adapter = request.app.state.ros2_adapter
    if adapter is None:
        raise HTTPException(status_code=423, detail="Nav2 导航仅适用于 ROS2 真机模式")
    return adapter.navigation_status()


@router.post("/navigation/goal", response_model=NavigationStatus)
async def navigation_goal(request: Request, goal: NavigationGoalRequest) -> NavigationStatus:
    adapter = request.app.state.ros2_adapter
    if adapter is None or not request.app.state.settings.ros2.allow_motion_commands:
        raise HTTPException(status_code=423, detail="真机导航指令已锁定")
    # Do not put an SSH process-status request on the motion-critical path.
    # The ROS2 adapter already requires fresh local watchdog, map/TF and
    # industrial-PC relay readiness before it publishes a goal. The module
    # panel continues to poll SSH status independently for operator feedback.
    return await adapter.send_navigation_goal(goal.x, goal.y, goal.yaw, goal.frame_id)


@router.post("/navigation/cancel", response_model=NavigationStatus)
async def cancel_navigation(request: Request) -> NavigationStatus:
    adapter = request.app.state.ros2_adapter
    if adapter is None:
        raise HTTPException(status_code=423, detail="Nav2 导航仅适用于 ROS2 真机模式")
    return await adapter.cancel_navigation()
