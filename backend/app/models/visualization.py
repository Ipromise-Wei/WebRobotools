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
    origin_yaw: float = 0.0
    data: list[int] = Field(default_factory=list)
    path: list[Point2D] = Field(default_factory=list)
    revision: int = 0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NavigationGoalRequest(BaseModel):
    x: float = Field(ge=-10000, le=10000, allow_inf_nan=False)
    y: float = Field(ge=-10000, le=10000, allow_inf_nan=False)
    yaw: float = Field(ge=-3.141593, le=3.141593, allow_inf_nan=False)
    frame_id: str = Field(default="map", min_length=1, max_length=80)


class NavigationStatus(BaseModel):
    phase: str = "idle"
    message: str = "尚未设置导航目标"
    x: float | None = None
    y: float | None = None
    yaw: float | None = None


class VisualizationConfig(BaseModel):
    camera_stream_url: str = ""
    camera_enabled: bool = False
    camera_connected: bool = False
    camera_serial: str = ""
    camera_error: str = ""
    map_topic: str
    plan_topic: str
    motion_commands_enabled: bool
    navigation_ready: bool = False
    navigation_reason: str = ""


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
