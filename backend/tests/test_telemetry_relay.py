import json
from types import SimpleNamespace

import pytest


pytest.importorskip("rclpy")

from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import OccupancyGrid, Path

from app.telemetry_relay import display_map, display_path


def test_display_map_is_bounded_before_crossing_network() -> None:
    source = OccupancyGrid()
    source.info.width = 4
    source.info.height = 4
    source.info.resolution = 0.05
    source.data = list(range(16))

    preview = display_map(source, 4)

    assert preview is not None
    assert (preview.info.width, preview.info.height) == (2, 2)
    assert preview.info.resolution == pytest.approx(0.1)
    assert list(preview.data) == [0, 2, 8, 10]


def test_display_path_preserves_endpoints_with_bounded_payload() -> None:
    source = Path()
    for index in range(9):
        pose = PoseStamped()
        pose.pose.position.x = float(index)
        source.poses.append(pose)

    preview = display_path(source, 3)

    assert [pose.pose.position.x for pose in preview.poses] == [0.0, 4.0, 8.0]


def test_cancel_tombstone_rejects_a_goal_arriving_on_the_other_topic_later() -> None:
    """Cancellation and goals have independent DDS ordering guarantees."""
    from app.telemetry_relay import IndustrialTelemetryRelay

    relay = IndustrialTelemetryRelay.__new__(IndustrialTelemetryRelay)
    relay._cancel_requested = {}
    relay._generation = None
    relay._request_id = None
    statuses: list[tuple[object, ...]] = []
    relay._status = lambda *args, **kwargs: statuses.append(args + (kwargs,))

    request_id = "server-session:1"
    relay._cancel_received(
        SimpleNamespace(data=json.dumps({"generation": 1, "request_id": request_id}))
    )
    relay._goal_received(
        SimpleNamespace(
            data=json.dumps(
                {
                    "generation": 1,
                    "request_id": request_id,
                    "x": 1.0,
                    "y": 2.0,
                    "yaw": 0.0,
                    "frame_id": "map",
                }
            )
        )
    )

    assert request_id in relay._cancel_requested
    assert statuses[0][0:4] == ("canceled", "目标已在传输途中取消", 1, request_id)
