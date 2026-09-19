from typing import Literal

from pydantic import BaseModel, Field


class GripperState(BaseModel):
    connected: bool = False
    status: Literal["opened", "closed", "stopped"] = "stopped"
    position: float = Field(default=0.0, ge=0.0, le=1.0)
    moving: bool = False

