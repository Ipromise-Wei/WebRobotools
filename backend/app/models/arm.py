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


class ArmJointRequest(BaseModel):
    joint: int = Field(ge=1, le=6)
    position: float = Field(ge=-360.0, le=360.0)


class ArmJointsRequest(BaseModel):
    positions: list[float]

    @field_validator("positions")
    @classmethod
    def validate_positions(cls, value: list[float]) -> list[float]:
        if len(value) != 6:
            raise ValueError("positions must contain exactly six joint values")
        if any(position < -360.0 or position > 360.0 for position in value):
            raise ValueError("joint positions must be between -360 and 360 degrees")
        return value


class ArmPoseRequest(Pose):
    pass

