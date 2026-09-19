from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Point2D(BaseModel):
    x: float
    y: float


class MapSnapshot(BaseModel):
    frame_id: str = "map"
    width: int = 0
    height: int = 0
    resolution: float = 0.05
    origin_x: float = 0.0
    origin_y: float = 0.0
    data: list[int] = Field(default_factory=list)
    path: list[Point2D] = Field(default_factory=list)
    revision: int = 0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VisualizationConfig(BaseModel):
    camera_stream_url: str = ""
    map_topic: str
    plan_topic: str
    motion_commands_enabled: bool
