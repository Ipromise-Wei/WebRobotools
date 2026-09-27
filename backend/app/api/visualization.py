from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.dependencies import get_map_manager
from app.core.map_manager import MapManager
from app.models.visualization import CameraStreamStatus, NavigationGoalRequest, NavigationStatus, VisualizationConfig

router = APIRouter()


@router.get("/config", response_model=VisualizationConfig)
async def config(request: Request) -> VisualizationConfig:
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
    try:
        runtime = await request.app.state.remote_runtime.status()
    except OSError as exc:
        raise HTTPException(status_code=423, detail=f"无法确认工控机安全模块状态：{exc}") from exc
    running = {task.id for task in runtime.tasks if task.state == "running"}
    if runtime.legacy_can0_active:
        raise HTTPException(status_code=423, detail="旧版 Web CAN0 管理任务仍在运行，请先按现场流程退出旧任务并恢复 CAN0 后再导航")
    if not runtime.reachable or not {"chassis", "navigation"}.issubset(running):
        raise HTTPException(status_code=423, detail="请先确认工控机 CAN0 已由系统配置为 UP、500000 bit/s，并从模块面板启动底盘和 Nav2 导航")
    return await adapter.send_navigation_goal(goal.x, goal.y, goal.yaw, goal.frame_id)


@router.post("/navigation/cancel", response_model=NavigationStatus)
async def cancel_navigation(request: Request) -> NavigationStatus:
    adapter = request.app.state.ros2_adapter
    if adapter is None:
        raise HTTPException(status_code=423, detail="Nav2 导航仅适用于 ROS2 真机模式")
    return await adapter.cancel_navigation()
