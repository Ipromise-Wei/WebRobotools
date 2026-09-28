import asyncio
import base64
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import zlib

from app.adapters.ros2.node import ROS2NodeAdapter
from app.core.map_manager import MapManager
from app.core.map_transport import MAP_DATA_ENCODING, encode_map_grid
from app.core.realsense_stream import RealSenseStream
from app.core.config import RealSenseSettings
from app.core.state_manager import StateManager
from app.models.visualization import MapSnapshot


def map_message(data: list[int], width: int = 2, height: int = 2) -> SimpleNamespace:
    return SimpleNamespace(
        header=SimpleNamespace(frame_id="map"),
        info=SimpleNamespace(
            width=width,
            height=height,
            resolution=0.05,
            origin=SimpleNamespace(
                position=SimpleNamespace(x=0.0, y=0.0),
                orientation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
            ),
        ),
        data=data,
    )


def path_message(points: list[tuple[float, float]]) -> SimpleNamespace:
    return SimpleNamespace(
        poses=[
            SimpleNamespace(
                pose=SimpleNamespace(position=SimpleNamespace(x=x, y=y))
            )
            for x, y in points
        ]
    )


def test_map_callback_throttles_full_grid_replacement(monkeypatch) -> None:
    adapter = ROS2NodeAdapter.__new__(ROS2NodeAdapter)
    adapter.config = SimpleNamespace(map_snapshot_interval_s=1.0, web_map_max_cells=4)
    adapter._lock = threading.Lock()
    adapter._map = MapSnapshot()
    adapter._navigation_grid = None
    adapter._last_map = 0.0
    adapter._last_map_snapshot = 0.0
    ticks = iter((10.0, 10.2))
    monkeypatch.setattr("app.adapters.ros2.node.time.monotonic", lambda: next(ticks))

    adapter._on_map(map_message([0, 0, 0, 0]))
    first = adapter._map
    adapter._on_map(map_message([100, 100, 100, 100]))

    assert adapter._map is first
    assert adapter._map.data == [0, 0, 0, 0]
    assert adapter._last_map == 10.2


def test_large_map_is_downsampled_only_for_browser_display(monkeypatch) -> None:
    adapter = ROS2NodeAdapter.__new__(ROS2NodeAdapter)
    adapter.config = SimpleNamespace(map_snapshot_interval_s=1.0, web_map_max_cells=4)
    adapter._lock = threading.Lock()
    adapter._map = MapSnapshot()
    adapter._navigation_grid = None
    adapter._last_map = 0.0
    adapter._last_map_snapshot = 0.0
    monkeypatch.setattr("app.adapters.ros2.node.time.monotonic", lambda: 10.0)
    source = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]

    adapter._on_map(map_message(source, width=4, height=4))

    assert (adapter._map.width, adapter._map.height, adapter._map.resolution) == (2, 2, 0.1)
    assert adapter._map.data == [0, 2, 8, 10]
    assert adapter._navigation_grid is not None
    assert adapter._navigation_grid.data is source


def test_path_callback_is_rate_limited_and_downsampled_for_web(monkeypatch) -> None:
    adapter = ROS2NodeAdapter.__new__(ROS2NodeAdapter)
    adapter.config = SimpleNamespace(
        path_snapshot_interval_s=1.0,
        web_path_max_points=3,
    )
    adapter._lock = threading.Lock()
    adapter._map = MapSnapshot()
    adapter._last_path_snapshot = 0.0
    ticks = iter((10.0, 10.2))
    monkeypatch.setattr("app.adapters.ros2.node.time.monotonic", lambda: next(ticks))

    adapter._on_path(path_message([(float(index), 0.0) for index in range(9)]))
    first = adapter._map
    adapter._on_path(path_message([(99.0, 0.0)]))

    assert [(point.x, point.y) for point in first.path] == [
        (0.0, 0.0), (4.0, 0.0), (8.0, 0.0),
    ]
    assert adapter._map is first
    assert adapter._map.path_revision == 1


def test_map_manager_reuses_immutable_grid_snapshot() -> None:
    async def scenario() -> None:
        manager = MapManager()
        snapshot = MapSnapshot(data=[0] * 100)
        await manager.replace(snapshot)
        _, returned = await manager.snapshot()
        assert returned is snapshot
        assert returned.data is snapshot.data
        version, payload = await manager.transport_snapshot()
        assert version == 1
        assert payload["data_encoding"] == MAP_DATA_ENCODING
        grid_data = payload["data"]

        path_update = snapshot.model_copy(
            update={"path": [], "path_revision": snapshot.path_revision + 1}
        )
        await manager.replace(path_update)
        next_version, next_payload = await manager.transport_snapshot()
        assert next_version == 2
        assert next_payload["data"] == grid_data
        assert next_payload["path_revision"] == 1

    asyncio.run(scenario())

def test_map_transport_encodes_signed_cells_as_compressed_bytes() -> None:
    payload = encode_map_grid(MapSnapshot(width=3, height=1, data=[-1, 0, 100]))
    compressed = base64.b64decode(payload["data"])

    assert payload["data_encoding"] == MAP_DATA_ENCODING
    assert list(zlib.decompress(compressed)) == [255, 0, 100]


def test_idle_websocket_waits_emit_heartbeats_instead_of_raising() -> None:
    async def scenario() -> None:
        manager = MapManager()
        version, _ = await manager.transport_snapshot()
        with patch(
            "app.core.map_manager.asyncio.wait_for",
            new=AsyncMock(side_effect=asyncio.TimeoutError),
        ):
            next_version, _ = await manager.wait_for_transport_update(version)
        assert next_version == version

        state = StateManager()
        with patch(
            "app.core.state_manager.asyncio.wait_for",
            new=AsyncMock(side_effect=asyncio.TimeoutError),
        ):
            state_version, _ = await state.wait_for_update(0)
        assert state_version == 0

    asyncio.run(scenario())


def test_camera_capture_waits_for_a_browser_stream_request() -> None:
    async def scenario() -> None:
        stream = RealSenseStream(RealSenseSettings(enabled=True))
        await stream.start()
        assert stream._thread is None
        await stream.stop()

    asyncio.run(scenario())
