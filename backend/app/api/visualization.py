from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.dependencies import get_map_manager
from app.core.map_manager import MapManager
from app.models.visualization import MapSnapshot, VisualizationConfig

router = APIRouter()


@router.get("/config", response_model=VisualizationConfig)
async def config(request: Request) -> VisualizationConfig:
    settings = request.app.state.settings
    return VisualizationConfig(
        camera_stream_url=settings.visualization.camera_stream_url,
        map_topic=settings.ros2.map_topic,
        plan_topic=settings.ros2.plan_topic,
        motion_commands_enabled=settings.ros2.allow_motion_commands,
    )


@router.get("/map", response_model=MapSnapshot)
async def current_map(manager: Annotated[MapManager, Depends(get_map_manager)]) -> MapSnapshot:
    _, snapshot = await manager.snapshot()
    return snapshot
