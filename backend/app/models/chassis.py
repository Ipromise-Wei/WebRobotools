from pydantic import BaseModel, Field


class ChassisState(BaseModel):
    connected: bool = False
    linear_velocity: float = 0.0
    angular_velocity: float = 0.0
    moving: bool = False


class ChassisMoveRequest(BaseModel):
    linear: float = Field(ge=-1.0, le=1.0)
    angular: float = Field(ge=-2.0, le=2.0)

