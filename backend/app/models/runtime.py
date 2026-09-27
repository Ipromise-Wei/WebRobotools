from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


RuntimePhase = Literal["disabled", "unconfigured", "offline", "stopped", "starting", "running", "stopping", "error"]


class RuntimeTaskState(BaseModel):
    id: str
    label: str
    state: Literal["pending", "starting", "running", "stopping", "stopped", "error"] = "pending"
    pid: int | None = None
    message: str = ""
    dependencies: list[str] = Field(default_factory=list)


class RuntimeStatus(BaseModel):
    agent_version: int = 0
    orchestrating: bool = False
    enabled: bool = False
    reachable: bool = False
    legacy_can0_active: bool = False
    phase: RuntimePhase = "disabled"
    host: str = ""
    message: str = ""
    supervisor_pid: int | None = None
    tasks: list[RuntimeTaskState] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RuntimeLog(BaseModel):
    lines: list[str] = Field(default_factory=list)


class RuntimeActionResponse(BaseModel):
    success: bool
    status: RuntimeStatus


class MapSaveRequest(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class MapImportRequest(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    yaml_base64: str = Field(min_length=1, max_length=2_000_000)
    pgm_base64: str = Field(min_length=1, max_length=32_000_000)


class MapLibrary(BaseModel):
    maps: list[str] = Field(default_factory=list)
