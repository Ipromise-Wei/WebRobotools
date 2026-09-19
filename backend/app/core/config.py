from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field


class ServerSettings(BaseModel):
    app_name: str = "Robot Web Control"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


class RobotSettings(BaseModel):
    mode: Literal["mock", "ros2"] = "mock"
    state_poll_interval: float = Field(default=0.2, gt=0.05, le=2.0)


class ROS2Settings(BaseModel):
    node_name: str = "robot_web_control"
    cmd_vel_topic: str = "/cmd_vel"
    odom_topic: str = "/odom"
    battery_topic: str = "/battery_state"
    map_topic: str = "/map"
    plan_topic: str = "/plan"
    allow_motion_commands: bool = False
    command_timeout: float = Field(default=0.5, ge=0.1, le=2.0)


class VisualizationSettings(BaseModel):
    camera_stream_url: str = ""


class Settings(BaseModel):
    server: ServerSettings = Field(default_factory=ServerSettings)
    robot: RobotSettings = Field(default_factory=RobotSettings)
    ros2: ROS2Settings = Field(default_factory=ROS2Settings)
    visualization: VisualizationSettings = Field(default_factory=VisualizationSettings)


@lru_cache
def get_settings() -> Settings:
    config_path = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
    if not config_path.exists():
        return Settings()
    with config_path.open("r", encoding="utf-8") as config_file:
        raw: dict[str, Any] = yaml.safe_load(config_file) or {}
    return Settings.model_validate(raw)
