import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import yaml

from app.core.config import Settings
from app.core.map_manager import MapManager
from app.main import initialize_default_runtime
from app.models.visualization import MapSnapshot, Point2D


class FakeMapAdapter:
    def __init__(self) -> None:
        self.clears = 0

    def clear_map_cache(self) -> MapSnapshot:
        self.clears += 1
        return MapSnapshot(revision=self.clears, path_revision=self.clears)


def test_production_runtime_defaults_to_navigation_without_slam() -> None:
    config_path = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
    settings = Settings.model_validate(yaml.safe_load(config_path.read_text(encoding="utf-8")))
    runtime = settings.remote_runtime
    profiles = {profile.id: profile.tasks for profile in runtime.profiles}
    tasks = {task.id: task for task in runtime.tasks}

    assert runtime.startup_profile == "basic_modules"
    assert profiles["basic_modules"] == [
        "chassis", "lidar", "localization", "laser_scan",
        "telemetry_relay", "navigation",
    ]
    assert profiles["manual_mapping"] == ["slam"]
    assert profiles["automatic_mapping"] == ["slam", "frontier_exploration"]
    assert tasks["slam"].include_in_start_all is False
    assert "slam" not in tasks["navigation"].dependencies
    assert "slam" not in tasks["telemetry_relay"].dependencies


def test_default_runtime_clears_history_before_enabling_map_polling() -> None:
    async def scenario() -> None:
        manager = MapManager()
        await manager.replace(MapSnapshot(
            width=2,
            height=2,
            data=[0, 0, 100, -1],
            path=[Point2D(x=1, y=1)],
            revision=8,
            path_revision=4,
        ))
        adapter = FakeMapAdapter()
        runtime = AsyncMock()
        visualization = AsyncMock()

        await initialize_default_runtime(
            runtime,
            "basic_modules",
            adapter,  # type: ignore[arg-type]
            manager,
            visualization,
        )

        runtime.restart_profile.assert_awaited_once_with("basic_modules")
        visualization.start.assert_awaited_once()
        _, snapshot = await manager.snapshot()
        assert snapshot.width == 0
        assert snapshot.height == 0
        assert snapshot.data == []
        assert snapshot.path == []
        assert adapter.clears == 1

    asyncio.run(scenario())


def test_default_runtime_keeps_map_polling_disabled_until_cleanup_succeeds() -> None:
    async def scenario() -> None:
        manager = MapManager()
        adapter = FakeMapAdapter()
        runtime = AsyncMock()
        runtime.restart_profile.side_effect = [OSError("offline"), AsyncMock()]
        visualization = AsyncMock()

        with patch("app.main.asyncio.sleep", new=AsyncMock()) as retry_sleep:
            await initialize_default_runtime(
                runtime,
                "basic_modules",
                adapter,  # type: ignore[arg-type]
                manager,
                visualization,
            )

        assert runtime.restart_profile.await_count == 2
        retry_sleep.assert_awaited_once_with(10)
        visualization.start.assert_awaited_once()
        # One clear follows the failed attempt and another closes the small
        # race between successful remote startup and enabling map polling.
        assert adapter.clears == 2

    asyncio.run(scenario())
