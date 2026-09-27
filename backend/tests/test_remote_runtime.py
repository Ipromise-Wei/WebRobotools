import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import RemoteRuntimeSettings
from app.core.remote_runtime import RemoteRuntimeError, RemoteRuntimeManager


class TimedOutProcess:
    def __init__(self) -> None:
        self.returncode: int | None = None
        self.killed = False
        self.waited = False

    async def communicate(self) -> tuple[bytes, bytes]:
        await asyncio.sleep(60)
        return b"", b""

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    async def wait(self) -> int:
        self.waited = True
        return self.returncode or 0


async def _run_timeout_scenario() -> None:
    process = TimedOutProcess()
    manager = RemoteRuntimeManager(
        RemoteRuntimeSettings(enabled=True, host="robot.example", user="robot")
    )
    with (
        patch(
            "app.core.remote_runtime.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=process),
        ),
        patch(
            "app.core.remote_runtime.asyncio.wait_for",
            new=AsyncMock(side_effect=asyncio.TimeoutError),
        ),
        pytest.raises(RemoteRuntimeError, match="industrial PC command timed out"),
    ):
        await manager._execute("status", timeout=0.01)
    assert process.killed
    assert process.waited


def test_ssh_timeout_becomes_runtime_error() -> None:
    asyncio.run(_run_timeout_scenario())
