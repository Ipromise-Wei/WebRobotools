from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.models.arm import ArmState
from app.models.chassis import ChassisState
from app.models.gripper import GripperState


class SystemState(BaseModel):
    backend: bool = True
    ros2: bool = False
    mode: Literal["mock", "ros2"] = "mock"


class RobotState(BaseModel):
    system: SystemState = Field(default_factory=SystemState)
    chassis: ChassisState = Field(default_factory=ChassisState)
    arm: ArmState = Field(default_factory=ArmState)
    gripper: GripperState = Field(default_factory=GripperState)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CommandResponse(BaseModel):
    success: bool = True
    state: RobotState

