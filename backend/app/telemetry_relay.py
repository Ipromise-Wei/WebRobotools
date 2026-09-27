#!/usr/bin/env python3
"""Keep robot-control traffic local to the industrial PC.

The Web server must not subscribe to the full-resolution ``/map`` or an
unbounded Nav2 ``/plan`` over the same DDS network used for navigation.  This
small IPC-side relay consumes those topics locally, then republishes a bounded
display-only version for the Web server.  Navigation goals are also accepted
locally and forwarded to Nav2 locally, so packet loss in video or map traffic
cannot interrupt the action/control loop.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from typing import Any

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid, Path
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool, String


def display_map(message: OccupancyGrid, maximum_cells: int) -> OccupancyGrid | None:
    """Make a bounded display map without moving the raw grid over the LAN.

    This map is explicitly not used for goal safety validation.  Validation is
    performed against ``self._raw_map`` on the industrial PC before a goal is
    passed to Nav2.
    """
    width, height = int(message.info.width), int(message.info.height)
    expected = width * height
    if width <= 0 or height <= 0 or expected != len(message.data):
        return None
    stride = max(1, math.ceil(math.sqrt(expected / maximum_cells)))
    result = OccupancyGrid()
    result.header = message.header
    result.info.map_load_time = message.info.map_load_time
    result.info.resolution = message.info.resolution * stride
    result.info.width = math.ceil(width / stride)
    result.info.height = math.ceil(height / stride)
    result.info.origin = message.info.origin
    # Sampling is for rendering only.  It is O(the output grid), rather than
    # O(the raw grid), so it cannot become a new navigation CPU bottleneck.
    data = message.data
    result.data = [
        int(data[row * width + column])
        for row in range(0, height, stride)
        for column in range(0, width, stride)
    ]
    return result


def display_path(message: Path, maximum_points: int) -> Path:
    """Return an endpoint-preserving, display-only path."""
    result = Path()
    result.header = message.header
    count = len(message.poses)
    if count <= maximum_points:
        result.poses = list(message.poses)
        return result
    step = (count - 1) / (maximum_points - 1)
    result.poses = [message.poses[round(index * step)] for index in range(maximum_points)]
    return result


class IndustrialTelemetryRelay(Node):
    """Relay bounded telemetry and own the local NavigateToPose client."""

    def __init__(self, options: argparse.Namespace) -> None:
        super().__init__("webrobot_telemetry_relay")
        self.options = options
        self._raw_map: OccupancyGrid | None = None
        self._last_raw_map_at = 0.0
        self._last_map = 0.0
        self._last_path = 0.0
        self._active_goal: Any = None
        self._generation: int | None = None
        self._request_id: str | None = None
        self._goal_coordinates: tuple[float, float, float] | None = None
        # DDS preserves order within a topic, but a cancel and a goal use two
        # distinct topics.  Retain short-lived cancellation tombstones so an
        # out-of-order cancel can never allow a late goal to start driving.
        self._cancel_requested: dict[str, float] = {}
        self._web_navigation_active = False
        self._last_web_navigation_active = 0.0

        # A display frame is disposable.  Best-effort/depth-one prevents a
        # slow Ethernet receiver from accumulating map fragments or triggering
        # reliable retransmission ahead of tiny control packets.
        display_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )
        self._map_publisher = self.create_publisher(
            OccupancyGrid, options.web_map_topic, display_qos
        )
        self._path_publisher = self.create_publisher(Path, options.web_path_topic, display_qos)
        self._status_publisher = self.create_publisher(String, options.status_topic, 10)
        self._ready_publisher = self.create_publisher(Bool, options.ready_topic, 10)

        map_input_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            # Receive the most recently latched SLAM map on relay startup,
            # while still allowing overloaded display frames to be dropped.
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.create_subscription(OccupancyGrid, options.map_topic, self._map_received, map_input_qos)
        self.create_subscription(Path, options.path_topic, self._path_received, display_qos)
        self.create_subscription(String, options.goal_topic, self._goal_received, 10)
        self.create_subscription(String, options.cancel_topic, self._cancel_received, 10)
        # This is an explicit stop edge and a low-rate control lease from the
        # Web service. It never gates local Nav2 velocity; a much longer lease
        # only cancels an unattended action after a real Web-server outage.
        self.create_subscription(String, options.web_active_topic, self._web_active_received, 10)

        self._action = NavigateToPose
        self._goal_status = GoalStatus
        self._client = ActionClient(self, NavigateToPose, options.navigate_action)
        self.create_timer(0.2, self._publish_ready)
        self.create_timer(1.0, self._enforce_web_lease)
        self.get_logger().info(
            f"Web telemetry relay ready: raw {options.map_topic}/{options.path_topic} "
            f"-> display {options.web_map_topic}/{options.web_path_topic}"
        )

    def _map_received(self, message: OccupancyGrid) -> None:
        self._raw_map = message
        now = time.monotonic()
        self._last_raw_map_at = now
        if now - self._last_map < self.options.map_interval:
            return
        preview = display_map(message, self.options.max_map_cells)
        if preview is None:
            self.get_logger().warning("ignored malformed OccupancyGrid")
            return
        self._last_map = now
        self._map_publisher.publish(preview)

    def _path_received(self, message: Path) -> None:
        now = time.monotonic()
        if now - self._last_path < self.options.path_interval:
            return
        self._last_path = now
        self._path_publisher.publish(display_path(message, self.options.max_path_points))

    def _publish_ready(self) -> None:
        message = Bool()
        message.data = self._client.server_is_ready()
        self._ready_publisher.publish(message)

    def _status(
        self,
        phase: str,
        message: str,
        generation: int,
        request_id: str,
        *,
        x: float | None = None,
        y: float | None = None,
        yaw: float | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "phase": phase,
            "message": message,
            "generation": generation,
            "request_id": request_id,
            "x": x,
            "y": y,
            "yaw": yaw,
        }
        output = String()
        output.data = json.dumps(payload, separators=(",", ":"))
        self._status_publisher.publish(output)

    def _validate_goal(self, x: float, y: float, frame_id: str) -> str | None:
        grid = self._raw_map
        if grid is None or not grid.data:
            return "等待工控机本地 SLAM 地图"
        if time.monotonic() - self._last_raw_map_at > 30.0:
            return "工控机本地地图已超过 30 秒未更新"
        if (grid.header.frame_id or "map") != frame_id:
            return "导航目标坐标系与工控机地图不匹配"
        resolution = grid.info.resolution
        if resolution <= 0:
            return "工控机地图分辨率无效"
        q = grid.info.origin.orientation
        origin_yaw = math.atan2(
            2 * (q.w * q.z + q.x * q.y),
            1 - 2 * (q.y * q.y + q.z * q.z),
        )
        if abs(origin_yaw) > 0.001:
            return "地图原点存在旋转，当前 Web 地图暂不支持安全选点"
        column = math.floor((x - grid.info.origin.position.x) / resolution)
        row = math.floor((y - grid.info.origin.position.y) / resolution)
        if not 0 <= column < grid.info.width or not 0 <= row < grid.info.height:
            return "导航目标在地图范围外"
        if grid.data[row * grid.info.width + column] != 0:
            return "目标点不是已知空闲区域"
        return None

    def _prune_cancel_requests(self) -> None:
        expires_before = time.monotonic() - 60.0
        for request_id, requested_at in list(self._cancel_requested.items()):
            if requested_at < expires_before:
                del self._cancel_requested[request_id]

    def _remember_cancel_request(self, request_id: str) -> None:
        self._prune_cancel_requests()
        self._cancel_requested[request_id] = time.monotonic()

    def _current_coordinates(self) -> tuple[float | None, float | None, float | None]:
        if self._goal_coordinates is None:
            return None, None, None
        return self._goal_coordinates

    def _request_cancel(self, message: str) -> None:
        generation = self._generation
        request_id = self._request_id
        if generation is None or request_id is None:
            return
        self._remember_cancel_request(request_id)
        x, y, yaw = self._current_coordinates()
        self._status("canceling", message, generation, request_id, x=x, y=y, yaw=yaw)
        if self._active_goal is None:
            return
        try:
            self._active_goal.cancel_goal_async()
        except Exception as exc:
            self._status(
                "failed",
                f"工控机取消导航异常：{exc}",
                generation,
                request_id,
                x=x,
                y=y,
                yaw=yaw,
            )

    def _enforce_web_lease(self) -> None:
        """Stop a local action if its Web control lease truly disappears.

        Navigation velocity itself never depends on this timer: the local
        watchdog still drops stale Nav2 velocity after 0.5 s.  This longer
        lease protects against an unattended action after a Web-server crash
        without reacting to ordinary network jitter or a discarded map frame.
        """
        if (
            self._generation is not None
            and self._web_navigation_active
            and time.monotonic() - self._last_web_navigation_active
            > self.options.web_lease_timeout
        ):
            self._web_navigation_active = False
            self._request_cancel("Web 导航控制租约超时，已请求停止")

    def _goal_received(self, message: String) -> None:
        try:
            payload = json.loads(message.data)
            generation = int(payload["generation"])
            request_id = str(payload["request_id"])
            x, y, yaw = float(payload["x"]), float(payload["y"]), float(payload["yaw"])
            frame_id = str(payload.get("frame_id", "map"))
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            self.get_logger().warning("ignored malformed Web navigation goal")
            return
        if not request_id or len(request_id) > 128:
            self.get_logger().warning("ignored navigation goal with invalid request id")
            return
        if not all(math.isfinite(value) for value in (x, y, yaw)) or abs(yaw) > math.pi:
            self._status("failed", "导航目标数值无效", generation, request_id)
            return
        self._prune_cancel_requests()
        if request_id in self._cancel_requested:
            self._status(
                "canceled",
                "目标已在传输途中取消",
                generation,
                request_id,
                x=x,
                y=y,
                yaw=yaw,
            )
            return
        if self._active_goal is not None or self._generation is not None:
            self._status("failed", "工控机已有导航目标，请先取消", generation, request_id)
            return
        error = self._validate_goal(x, y, frame_id)
        if error:
            self._status("failed", error, generation, request_id, x=x, y=y, yaw=yaw)
            return
        if not self._client.server_is_ready():
            self._status(
                "failed",
                "工控机 Nav2 NavigateToPose 未就绪",
                generation,
                request_id,
                x=x,
                y=y,
                yaw=yaw,
            )
            return

        goal = self._action.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = frame_id
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = x
        goal.pose.pose.position.y = y
        goal.pose.pose.orientation.z = math.sin(yaw / 2)
        goal.pose.pose.orientation.w = math.cos(yaw / 2)
        self._generation = generation
        self._request_id = request_id
        self._goal_coordinates = (x, y, yaw)
        # The goal itself starts the first control lease. The regular
        # request-correlated JSON lease refreshes it afterwards.
        self._web_navigation_active = True
        self._last_web_navigation_active = time.monotonic()
        self._status("sending", "工控机正在提交 Nav2 目标", generation, request_id, x=x, y=y, yaw=yaw)
        try:
            response = self._client.send_goal_async(goal)
            response.add_done_callback(
                lambda future: self._goal_response(future, generation, request_id, x, y, yaw)
            )
        except Exception as exc:
            self._generation = None
            self._request_id = None
            self._goal_coordinates = None
            self._status(
                "failed",
                f"工控机 Nav2 目标提交异常：{exc}",
                generation,
                request_id,
                x=x,
                y=y,
                yaw=yaw,
            )

    def _goal_response(
        self, future: Any, generation: int, request_id: str, x: float, y: float, yaw: float
    ) -> None:
        try:
            handle = future.result()
        except Exception as exc:
            if self._generation == generation and self._request_id == request_id:
                self._generation = None
                self._request_id = None
                self._goal_coordinates = None
                self._status(
                    "failed",
                    f"工控机 Nav2 目标响应异常：{exc}",
                    generation,
                    request_id,
                    x=x,
                    y=y,
                    yaw=yaw,
                )
            return
        if self._generation != generation or self._request_id != request_id:
            if handle.accepted:
                handle.cancel_goal_async()
            return
        if request_id in self._cancel_requested:
            if not handle.accepted:
                self._generation = None
                self._request_id = None
                self._goal_coordinates = None
                self._status("canceled", "导航已取消", generation, request_id, x=x, y=y, yaw=yaw)
                return
            self._active_goal = handle
            self._status("canceling", "工控机正在取消导航", generation, request_id, x=x, y=y, yaw=yaw)
            handle.cancel_goal_async()
            handle.get_result_async().add_done_callback(
                lambda result: self._goal_result(result, generation, request_id, x, y, yaw)
            )
            return
        if not handle.accepted:
            self._generation = None
            self._request_id = None
            self._goal_coordinates = None
            self._status("failed", "工控机 Nav2 拒绝导航目标", generation, request_id, x=x, y=y, yaw=yaw)
            return
        self._active_goal = handle
        self._status("navigating", "导航中", generation, request_id, x=x, y=y, yaw=yaw)
        handle.get_result_async().add_done_callback(
            lambda result: self._goal_result(result, generation, request_id, x, y, yaw)
        )

    def _goal_result(
        self, future: Any, generation: int, request_id: str, x: float, y: float, yaw: float
    ) -> None:
        if self._generation != generation or self._request_id != request_id:
            return
        try:
            result = future.result()
            status = result.status
            phase = (
                "succeeded" if status == self._goal_status.STATUS_SUCCEEDED
                else "canceled" if status == self._goal_status.STATUS_CANCELED
                else "failed"
            )
            detail = "已到达目标" if phase == "succeeded" else "导航已取消" if phase == "canceled" else f"导航失败，状态码 {status}"
        except Exception as exc:
            phase, detail = "failed", f"导航结果异常：{exc}"
        self._active_goal = None
        self._generation = None
        self._request_id = None
        self._goal_coordinates = None
        self._cancel_requested.pop(request_id, None)
        self._status(phase, detail, generation, request_id, x=x, y=y, yaw=yaw)

    def _cancel_received(self, message: String) -> None:
        try:
            payload = json.loads(message.data)
            generation = int(payload["generation"])
            request_id = str(payload["request_id"])
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            return
        if not request_id or len(request_id) > 128:
            return
        self._remember_cancel_request(request_id)
        if generation != self._generation or request_id != self._request_id:
            return
        self._request_cancel("工控机正在取消导航")

    def _web_active_received(self, message: String) -> None:
        try:
            payload = json.loads(message.data)
            active = bool(payload["active"])
            request_id = str(payload["request_id"])
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            self.get_logger().warning("ignored malformed Web navigation lease")
            return
        # A stale lease from a previous goal must never affect a new action.
        if request_id != self._request_id:
            return
        if active:
            self._web_navigation_active = True
            self._last_web_navigation_active = time.monotonic()
            return
        if self._web_navigation_active and self._generation is not None:
            # An explicit false is sent for a normal Web shutdown.  Do not use
            # a 0.5-second velocity timeout here: a normal map/video delay
            # must not create a stop pulse during a valid local action.
            self._request_cancel("Web 服务请求停止导航")
        self._web_navigation_active = False


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map-topic", default="/map")
    parser.add_argument("--path-topic", default="/plan")
    parser.add_argument("--web-map-topic", default="/webrobot/web_map")
    parser.add_argument("--web-path-topic", default="/webrobot/web_plan")
    parser.add_argument("--goal-topic", default="/webrobot/navigation/goal")
    parser.add_argument("--cancel-topic", default="/webrobot/navigation/cancel")
    parser.add_argument("--status-topic", default="/webrobot/navigation/status")
    parser.add_argument("--ready-topic", default="/webrobot/navigation/ready")
    parser.add_argument("--web-active-topic", default="/webrobot/navigation/active")
    parser.add_argument("--navigate-action", default="/navigate_to_pose")
    parser.add_argument("--map-interval", type=float, default=1.0)
    parser.add_argument("--path-interval", type=float, default=0.5)
    parser.add_argument("--max-map-cells", type=int, default=65_536)
    parser.add_argument("--max-path-points", type=int, default=256)
    parser.add_argument("--web-lease-timeout", type=float, default=10.0)
    options = parser.parse_args()
    if options.map_interval < 0.1 or options.path_interval < 0.1:
        parser.error("relay intervals must be at least 0.1 seconds")
    if options.max_map_cells < 4096 or options.max_path_points < 2:
        parser.error("relay limits are too small")
    if options.web_lease_timeout < 2.0 or options.web_lease_timeout > 60.0:
        parser.error("web lease timeout must be between 2 and 60 seconds")
    return options


def main() -> None:
    options = arguments()
    rclpy.init()
    node: Any = IndustrialTelemetryRelay(options)
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
