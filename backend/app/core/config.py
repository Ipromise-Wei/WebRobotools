from functools import lru_cache
import math
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class ServerSettings(BaseModel):
    app_name: str = "Robot Web Control"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


class AuthSettings(BaseModel):
    enabled: bool = True
    credential_file: str = "config/auth.local.json"
    session_hours: int = Field(default=8, ge=1, le=24)
    cookie_secure: bool = False
    max_attempts: int = Field(default=5, ge=3, le=20)
    lockout_seconds: int = Field(default=300, ge=30, le=3600)


class RobotSettings(BaseModel):
    mode: Literal["mock", "ros2"] = "mock"
    state_poll_interval: float = Field(default=0.2, gt=0.05, le=2.0)


class ROS2Settings(BaseModel):
    node_name: str = "robot_web_control"
    cmd_vel_topic: str = "/webrobot/cmd_vel"
    odom_topic: str = "/odom"
    battery_topic: str = "/battery_state"
    # These are bounded display topics emitted by the industrial-PC relay.
    # The raw SLAM /map and /plan never cross the Web-server DDS connection.
    map_topic: str = "/webrobot/web_map"
    # The IPC relay owns the 2 Hz map cap; this short local guard only protects
    # against a misconfigured relay without needlessly dropping its latest UI
    # frame a second time.
    map_snapshot_interval_s: float = Field(default=0.2, ge=0.2, le=10.0)
    # 512 × 512 preserves thin walls and scan detail on a full-screen map
    # while still being a bounded display-only payload.
    web_map_max_cells: int = Field(default=262_144, ge=4_096, le=1_048_576)
    plan_topic: str = "/webrobot/web_plan"
    # Nav2 can publish long global plans many times per second. The IPC relay
    # owns the 0.5 Hz cap; this is only a local defensive guard.
    path_snapshot_interval_s: float = Field(default=0.1, ge=0.1, le=10.0)
    web_path_max_points: int = Field(default=256, ge=2, le=4_096)
    executor_threads: int = Field(default=3, ge=2, le=4)
    navigate_to_pose_action: str = "/navigate_to_pose"
    # Tiny JSON control messages and a request-correlated lease travel to the
    # IPC relay. The relay validates the raw local map and calls NavigateToPose
    # locally.
    navigation_goal_topic: str = "/webrobot/navigation/goal"
    navigation_cancel_topic: str = "/webrobot/navigation/cancel"
    navigation_status_topic: str = "/webrobot/navigation/status"
    navigation_ready_topic: str = "/webrobot/navigation/ready"
    navigation_active_topic: str = "/webrobot/navigation/active"
    allow_motion_commands: bool = False
    command_timeout: float = Field(default=0.5, ge=0.1, le=2.0)
    watchdog_status_topic: str = "/webrobot/cmd_vel_watchdog/ready"
    watchdog_timeout: float = Field(default=1.0, ge=0.2, le=5.0)

    @model_validator(mode="after")
    def validate_motion_topics(self) -> "ROS2Settings":
        if self.allow_motion_commands and (
            self.cmd_vel_topic != "/webrobot/cmd_vel"
            or self.navigation_goal_topic != "/webrobot/navigation/goal"
            or self.navigation_cancel_topic != "/webrobot/navigation/cancel"
            or self.navigation_status_topic != "/webrobot/navigation/status"
            or self.navigation_ready_topic != "/webrobot/navigation/ready"
            or self.navigation_active_topic != "/webrobot/navigation/active"
            or self.watchdog_status_topic != "/webrobot/cmd_vel_watchdog/ready"
        ):
            raise ValueError("实车速度、导航中继与看门狗必须使用工控机配套的固定安全话题")
        return self


class RealSenseSettings(BaseModel):
    enabled: bool = False
    source: Literal["local", "industrial_pc"] = "local"
    serial: str = ""
    video_device: str = Field(default="/dev/video4", pattern=r"^/dev/video[0-9]+$")
    input_format: Literal["yuyv422", "mjpeg"] = "yuyv422"
    width: int = Field(default=1280, ge=320, le=1920)
    height: int = Field(default=720, ge=240, le=1080)
    # A bounded preview must leave headroom for local Nav2 and avoid filling
    # the Ethernet queue used by small control messages.
    fps: int = Field(default=12, ge=1, le=60)
    jpeg_quality: int = Field(default=70, ge=40, le=95)
    max_frame_bytes: int = Field(default=800_000, ge=64_000, le=8_000_000)
    retry_interval_s: float = Field(default=2.0, ge=0.5, le=30)


class VisualizationSettings(BaseModel):
    camera_stream_url: str = ""
    realsense: RealSenseSettings = Field(default_factory=RealSenseSettings)


class ArmSettings(BaseModel):
    enabled: bool = False
    transport: Literal["direct", "industrial_pc"] = "direct"
    host: str = Field(default="192.168.1.20", min_length=1)
    port: int = Field(default=8080, ge=1, le=65535)
    network_interface: str = Field(
        default="",
        max_length=15,
        pattern=r"^[A-Za-z0-9_.:-]*$",
    )
    timeout_s: float = Field(default=2.0, ge=0.2, le=10)
    allow_motion_commands: bool = False
    expected_tool: str = ""
    collision_level: int = Field(default=8, ge=1, le=8)
    joint_speed_percent: int = Field(default=5, ge=1, le=100)
    pose_speed_percent: int = Field(default=5, ge=1, le=100)
    workspace_min_m: list[float] = Field(default_factory=lambda: [-0.8, -0.8, 0.05])
    workspace_max_m: list[float] = Field(default_factory=lambda: [0.8, 0.8, 1.0])
    clearance_m: float = Field(default=0.0, ge=0, le=0.2)
    max_pose_segment_m: float = Field(default=0.8, ge=0.02, le=0.8)
    keepout_enabled: bool = False
    keepout_min_m: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    keepout_max_m: list[float] = Field(default_factory=lambda: [0.1, 0.1, 0.1])
    standby_joints_deg: list[float] = Field(
        default_factory=lambda: [178.0, 37.258, -65.159, 4.531, -107.568, 6.608]
    )

    @field_validator(
        "workspace_min_m", "workspace_max_m", "keepout_min_m", "keepout_max_m"
    )
    @classmethod
    def validate_workspace_vector(cls, value: list[float]) -> list[float]:
        if len(value) != 3 or not all(math.isfinite(item) for item in value):
            raise ValueError("机械臂工作空间必须包含三个有限数值")
        return value

    @field_validator("standby_joints_deg")
    @classmethod
    def validate_standby_joints(cls, value: list[float]) -> list[float]:
        if len(value) != 6 or not all(math.isfinite(item) for item in value):
            raise ValueError("机械臂待命位必须包含六个有限关节角")
        return value

    @model_validator(mode="after")
    def validate_workspace_order(self) -> "ArmSettings":
        if any(low >= high for low, high in zip(self.workspace_min_m, self.workspace_max_m)):
            raise ValueError("机械臂工作空间下限必须小于上限")
        if any(low >= high for low, high in zip(self.keepout_min_m, self.keepout_max_m)):
            raise ValueError("机械臂禁止区域下限必须小于上限")
        if any(
            high - low <= 2 * self.clearance_m
            for low, high in zip(self.workspace_min_m, self.workspace_max_m)
        ):
            raise ValueError("机械臂工作空间过小，无法应用安全余量")
        return self


class GripperSettings(BaseModel):
    enabled: bool = False
    allow_commands: bool = False
    open_io: int = Field(default=1, ge=1, le=2)
    close_io: int = Field(default=2, ge=1, le=2)
    active_level: int = Field(default=0, ge=0, le=1)
    pulse_s: float = Field(default=1.0, ge=0.1, le=10)

    @model_validator(mode="after")
    def validate_channels(self) -> "GripperSettings":
        if self.open_io == self.close_io:
            raise ValueError("夹爪张开与闭合 IO 不能使用同一通道")
        return self


class RuntimeTaskSettings(BaseModel):
    id: str
    label: str
    command: str
    startup_delay: float = Field(default=2.0, ge=0, le=120)
    ready_command: str = ""
    ready_timeout: float = Field(default=0, ge=0, le=300)
    ready_probe_timeout: float = Field(default=15, ge=1, le=60)
    on_start_command: str = ""
    on_stop_command: str = ""
    include_in_start_all: bool = True
    dependencies: list[str] = Field(default_factory=list)


class RuntimeProfileSettings(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    label: str = Field(min_length=1, max_length=80)
    tasks: list[str] = Field(min_length=1)


class RemoteRuntimeSettings(BaseModel):
    enabled: bool = False
    host: str = ""
    user: str = ""
    port: int = Field(default=22, ge=1, le=65535)
    connect_timeout: float = Field(default=5.0, ge=1, le=30)
    agent_path: str = "/home/hzauaiot/.local/lib/webrobot/runtime_agent.py"
    domain_id: int = Field(default=30, ge=0, le=232)
    map_directory: str = "/home/hzauaiot/.local/share/webrobot/maps"
    startup_profile: str = Field(
        default="", pattern=r"^$|^[a-z][a-z0-9_-]{0,63}$"
    )
    environment_setup: list[str] = Field(default_factory=list)
    tasks: list[RuntimeTaskSettings] = Field(default_factory=list)
    profiles: list[RuntimeProfileSettings] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_runtime_graph(self) -> "RemoteRuntimeSettings":
        task_ids = {task.id for task in self.tasks}
        profile_ids = {profile.id for profile in self.profiles}
        if self.startup_profile and self.startup_profile not in profile_ids:
            raise ValueError("remote_runtime.startup_profile 必须引用已配置的运行方案")
        for task in self.tasks:
            unknown = set(task.dependencies) - task_ids
            if unknown:
                raise ValueError(f"运行任务 {task.id} 包含未知依赖：{', '.join(sorted(unknown))}")
        for profile in self.profiles:
            unknown = set(profile.tasks) - task_ids
            if unknown:
                raise ValueError(f"运行方案 {profile.id} 包含未知任务：{', '.join(sorted(unknown))}")
        return self


class Settings(BaseModel):
    server: ServerSettings = Field(default_factory=ServerSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    robot: RobotSettings = Field(default_factory=RobotSettings)
    ros2: ROS2Settings = Field(default_factory=ROS2Settings)
    visualization: VisualizationSettings = Field(default_factory=VisualizationSettings)
    arm: ArmSettings = Field(default_factory=ArmSettings)
    gripper: GripperSettings = Field(default_factory=GripperSettings)
    remote_runtime: RemoteRuntimeSettings = Field(default_factory=RemoteRuntimeSettings)

    @model_validator(mode="after")
    def validate_arm_transport(self) -> "Settings":
        if self.arm.enabled and self.arm.transport == "industrial_pc":
            if not self.arm.network_interface.strip():
                raise ValueError("工控机机械臂传输必须配置 network_interface")
            if (
                not self.remote_runtime.enabled
                or not self.remote_runtime.host.strip()
                or not self.remote_runtime.user.strip()
            ):
                raise ValueError("工控机机械臂传输必须启用并配置 remote_runtime SSH")
        camera = self.visualization.realsense
        if camera.enabled and camera.source == "industrial_pc":
            if (
                not self.remote_runtime.enabled
                or not self.remote_runtime.host.strip()
                or not self.remote_runtime.user.strip()
            ):
                raise ValueError("工控机 RealSense 采集必须启用并配置 remote_runtime SSH")
        return self


@lru_cache
def get_settings() -> Settings:
    config_path = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
    if not config_path.exists():
        return Settings()
    with config_path.open("r", encoding="utf-8") as config_file:
        raw: dict[str, Any] = yaml.safe_load(config_file) or {}
    return Settings.model_validate(raw)
