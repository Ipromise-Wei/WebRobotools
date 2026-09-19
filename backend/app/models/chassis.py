from pydantic import BaseModel, Field


class ChassisState(BaseModel):
    connected: bool = False
    linear_velocity: float = 0.0
    angular_velocity: float = 0.0
    moving: bool = False
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0
    odom_received: bool = False
    map_x: float = 0.0
    map_y: float = 0.0
    map_yaw: float = 0.0
    map_pose_received: bool = False
    battery_percentage: float | None = None
    battery_voltage: float | None = None


class ChassisMoveRequest(BaseModel):
    linear: float = Field(ge=-1.0, le=1.0)
    angular: float = Field(ge=-2.0, le=2.0)
