from pydantic import BaseModel, Field, field_validator


class Pose(BaseModel):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    rx: float = 0.0
    ry: float = 0.0
    rz: float = 0.0


class ArmState(BaseModel):
    connected: bool = False
    moving: bool = False
    joints: list[float] = Field(default_factory=lambda: [0.0] * 6)
    pose: Pose = Field(default_factory=Pose)
    work_frame: str = ""
    work_frame_safe: bool = False
    tool_frame: str = ""
    error: str = ""


class ArmJointRequest(BaseModel):
    joint: int = Field(ge=1, le=6)
    position: float = Field(ge=-360.0, le=360.0)
    speed: int = Field(default=5, ge=1, le=100)


class ArmJointsRequest(BaseModel):
    positions: list[float]
    speed: int = Field(default=5, ge=1, le=100)

    @field_validator("positions")
    @classmethod
    def validate_positions(cls, value: list[float]) -> list[float]:
        if len(value) != 6:
            raise ValueError("positions must contain exactly six joint values")
        if any(position < -360.0 or position > 360.0 for position in value):
            raise ValueError("joint positions must be between -360 and 360 degrees")
        return value


class ArmPoseRequest(Pose):
    speed: int = Field(default=5, ge=1, le=100)


class ArmConfigResponse(BaseModel):
    enabled: bool = False
    motion_commands_enabled: bool = False
    model: str = "RML63"
    transport: str = "direct"
    host: str = ""
    port: int = 8080
    network_interface: str = ""
    expected_tool: str = ""
    collision_level: int = 8
    joint_speed_percent: int = 5
    pose_speed_percent: int = 5
    workspace_min_m: list[float]
    workspace_max_m: list[float]
    max_pose_segment_m: float
    keepout_enabled: bool
    standby_joints_deg: list[float]
    gripper_enabled: bool = False
    gripper_commands_enabled: bool = False
