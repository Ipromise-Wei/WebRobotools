import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import RemoteRuntimeSettings, RuntimeProfileSettings, RuntimeTaskSettings
from app.core.remote_runtime import RemoteRuntimeError, RemoteRuntimeManager
from app.models.runtime import RuntimeStatus, RuntimeTaskState


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


def test_map_save_waits_for_slam_and_verifies_both_artifacts() -> None:
    async def scenario() -> None:
        settings = RemoteRuntimeSettings(
            enabled=True,
            host="robot.example",
            user="robot",
            map_directory="/robot/maps",
            tasks=[RuntimeTaskSettings(id="slam", label="SLAM", command="slam")],
        )
        manager = RemoteRuntimeManager(settings)
        status = RuntimeStatus(
            enabled=True,
            reachable=True,
            phase="running",
            tasks=[RuntimeTaskState(id="slam", label="SLAM", state="running")],
        )
        commands: list[tuple[str, float]] = []

        async def fake_status() -> RuntimeStatus:
            return status

        async def fake_execute(command: str, timeout: float = 15) -> str:
            commands.append((command, timeout))
            return "demo.yaml\n" if command.startswith("mkdir -p /robot/maps && find") else ""

        manager.status = fake_status  # type: ignore[method-assign]
        manager._execute = fake_execute  # type: ignore[method-assign]

        assert await manager.save_map("demo") == ["demo"]
        save_command = next(command for command, _ in commands if "map_saver_cli" in command)
        assert "save_map_timeout:=25.0" in save_command
        assert "map_subscribe_transient_local:=true" in save_command
        assert any("test -s /robot/maps/demo.yaml" in command for command, _ in commands)

    asyncio.run(scenario())


def test_frontier_stop_uses_the_configured_standard_control_command() -> None:
    async def scenario() -> None:
        settings = RemoteRuntimeSettings(
            enabled=True,
            host="robot.example",
            user="robot",
            tasks=[
                RuntimeTaskSettings(
                    id="frontier_exploration",
                    label="Frontier",
                    command="frontier",
                    on_stop_command="timeout 8 ros2 run frontier_exploration_ros2 frontier_exploration_ctl stop",
                )
            ],
        )
        manager = RemoteRuntimeManager(settings)
        current = RuntimeStatus(
            enabled=True,
            reachable=True,
            phase="running",
            tasks=[RuntimeTaskState(id="frontier_exploration", label="Frontier", state="running")],
        )
        commands: list[tuple[str, float]] = []

        async def fake_execute(command: str, timeout: float = 15) -> str:
            commands.append((command, timeout))
            return ""

        manager._execute = fake_execute  # type: ignore[method-assign]
        await manager._request_frontier_stop(current)

        assert commands and "frontier_exploration_ctl stop" in commands[0][0]
        assert commands[0][1] == 12

    asyncio.run(scenario())


def test_mapping_profile_restart_stops_only_session_before_starting_fresh() -> None:
    async def scenario() -> None:
        settings = RemoteRuntimeSettings(
            enabled=True,
            host="robot.example",
            user="robot",
            tasks=[
                RuntimeTaskSettings(
                    id="frontier_exploration",
                    label="Frontier",
                    command="frontier",
                    on_stop_command="ros2 run frontier_exploration_ros2 frontier_exploration_ctl stop",
                )
            ],
            profiles=[
                RuntimeProfileSettings(
                    id="automatic_mapping",
                    label="Automatic mapping",
                    tasks=["frontier_exploration"],
                )
            ],
        )
        manager = RemoteRuntimeManager(settings)
        current = RuntimeStatus(
            enabled=True,
            reachable=True,
            phase="running",
            tasks=[RuntimeTaskState(id="frontier_exploration", label="Frontier", state="running")],
        )
        commands: list[tuple[str, float]] = []

        async def fake_status() -> RuntimeStatus:
            return current

        async def fake_execute(command: str, timeout: float = 15) -> str:
            commands.append((command, timeout))
            return ""

        manager.status = fake_status  # type: ignore[method-assign]
        manager._deploy_agent = AsyncMock()  # type: ignore[method-assign]
        manager._execute = fake_execute  # type: ignore[method-assign]

        assert await manager.restart_profile("automatic_mapping") is current
        selective_stop_index = next(
            index for index, (command, _) in enumerate(commands)
            if "stop-tasks" in command
        )
        start_index = next(
            index for index, (command, _) in enumerate(commands)
            if "start-profile" in command
        )
        assert "frontier_exploration_ctl stop" in commands[0][0]
        assert "slam,telemetry_relay,navigation,frontier_exploration" in commands[selective_stop_index][0]
        assert commands[selective_stop_index][1] == 60
        assert selective_stop_index < start_index

    asyncio.run(scenario())
