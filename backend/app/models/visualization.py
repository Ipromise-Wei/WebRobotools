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
    camera_enabled: bool = False
    camera_connected: bool = False
    camera_serial: str = ""
    camera_error: str = ""
    map_topic: str
    plan_topic: str
    motion_commands_enabled: bool


class CameraStreamStatus(BaseModel):
    enabled: bool = False
    source: str = "local"
    connected: bool = False
    serial: str = ""
    width: int = 0
    height: int = 0
    fps: int = 0
    sequence: int = 0
    error: str = ""
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
