import threading

from app.adapters.ros2.node import ROS2NodeAdapter
from app.models.visualization import NavigationStatus


class FakeResultFuture:
    def __init__(self) -> None:
        self.callback = None

    def add_done_callback(self, callback):  # type: ignore[no-untyped-def]
        self.callback = callback


class FakeGoalHandle:
    accepted = True

    def __init__(self) -> None:
        self.cancelled = False
        self.result_future = FakeResultFuture()

    def cancel_goal_async(self) -> None:
        self.cancelled = True

    def get_result_async(self) -> FakeResultFuture:
        return self.result_future


class FakeGoalResponse:
    def __init__(self, handle: FakeGoalHandle) -> None:
        self.handle = handle

    def result(self) -> FakeGoalHandle:
        return self.handle


class FakeTimer:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


def adapter_with_pending_goal() -> ROS2NodeAdapter:
    adapter = ROS2NodeAdapter.__new__(ROS2NodeAdapter)
    adapter._lock = threading.Lock()
    adapter._nav_goal_timers = {1: FakeTimer()}
    adapter._expired_nav_generations = set()
    adapter._nav_generation = 1
    adapter._nav_status = NavigationStatus(phase="sending", message="等待 Nav2 接收目标")
    adapter._nav_goal_handle = None
    return adapter


def test_goal_response_transitions_to_navigation_without_http_wait() -> None:
    adapter = adapter_with_pending_goal()
    handle = FakeGoalHandle()

    adapter._goal_response(FakeGoalResponse(handle), 1)

    assert adapter._nav_status.phase == "navigating"
    assert adapter._nav_goal_handle is handle
    assert handle.result_future.callback is not None


def test_late_goal_response_is_cancelled_after_confirmation_timeout() -> None:
    adapter = adapter_with_pending_goal()
    handle = FakeGoalHandle()

    adapter._expire_navigation_goal_response(1)
    adapter._goal_response(FakeGoalResponse(handle), 1)

    assert adapter._nav_status.phase == "failed"
    assert "确认超时" in adapter._nav_status.message
    assert handle.cancelled
    assert adapter._nav_goal_handle is None
