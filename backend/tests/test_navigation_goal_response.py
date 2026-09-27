import json
import threading
from types import SimpleNamespace

from app.adapters.ros2.node import ROS2NodeAdapter
from app.models.visualization import NavigationStatus


class FakeString:
    def __init__(self) -> None:
        self.data = ""


class RecordingPublisher:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def publish(self, message: FakeString) -> None:
        self.messages.append(message.data)


class FakeTimer:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


def adapter_with_pending_goal() -> ROS2NodeAdapter:
    adapter = ROS2NodeAdapter.__new__(ROS2NodeAdapter)
    adapter._lock = threading.Lock()
    adapter._nav_goal_timers = {1: FakeTimer()}
    adapter._expired_nav_request_ids = set()
    adapter._nav_generation = 1
    adapter._nav_request_id = "server-session:1"
    adapter._nav_status = NavigationStatus(
        phase="sending", message="正在发送到工控机本地导航中继"
    )
    adapter._string = FakeString
    adapter._nav_cancel_publisher = RecordingPublisher()
    return adapter


def relay_status(request_id: str, phase: str) -> SimpleNamespace:
    return SimpleNamespace(
        data=json.dumps(
            {
                "generation": 1,
                "request_id": request_id,
                "phase": phase,
                "message": f"relay {phase}",
                "x": 1.0,
                "y": 2.0,
                "yaw": 0.0,
            }
        )
    )


def test_relay_sending_status_keeps_confirmation_timer_until_nav2_accepts() -> None:
    adapter = adapter_with_pending_goal()
    timer = adapter._nav_goal_timers[1]

    adapter._on_navigation_status(relay_status("server-session:1", "sending"))

    assert adapter._nav_status.phase == "sending"
    assert timer.cancelled is False
    assert 1 in adapter._nav_goal_timers

    adapter._on_navigation_status(relay_status("server-session:1", "navigating"))

    assert adapter._nav_status.phase == "navigating"
    assert timer.cancelled is True
    assert adapter._nav_goal_timers == {}


def test_delayed_status_from_an_old_web_process_is_ignored() -> None:
    adapter = adapter_with_pending_goal()

    adapter._on_navigation_status(relay_status("old-server-session:1", "navigating"))

    assert adapter._nav_status.phase == "sending"
    assert adapter._nav_goal_timers[1].cancelled is False


def test_confirmation_timeout_publishes_a_correlated_cancel_tombstone() -> None:
    adapter = adapter_with_pending_goal()

    adapter._expire_navigation_goal_response(1, "server-session:1")

    assert adapter._nav_status.phase == "failed"
    assert "确认超时" in adapter._nav_status.message
    assert "server-session:1" in adapter._expired_nav_request_ids
    assert len(adapter._nav_cancel_publisher.messages) == 1
    assert json.loads(adapter._nav_cancel_publisher.messages[0]) == {
        "generation": 1,
        "request_id": "server-session:1",
    }
