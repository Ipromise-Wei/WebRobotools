import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
import json
import math
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.config import ROS2Settings
from app.models.chassis import ChassisState
from app.models.visualization import MapSnapshot, NavigationStatus, Point2D


class MotionControlDisabled(RuntimeError):
    pass


@dataclass(frozen=True)
class _NavigationGrid:
    """Latest bounded relay grid used for UI readiness and display metadata."""

    frame_id: str
    width: int
    height: int
    resolution: float
    origin_x: float
    origin_y: float
    origin_yaw: float
    data: Sequence[int]


class ROS2NodeAdapter:
    def __init__(self, config: ROS2Settings) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._nav_command_lock = threading.Lock()
        self._running = False
        self._last_odom = 0.0
        self._last_map_pose = 0.0
        self._last_map = 0.0
        self._last_map_snapshot = 0.0
        self._last_path_snapshot = 0.0
        self._last_command = 0.0
        self._last_watchdog = 0.0
        self._velocity = (0.0, 0.0)
        self._state = ChassisState()
        self._map = MapSnapshot()
        self._navigation_grid: _NavigationGrid | None = None
        self._thread: threading.Thread | None = None
        self._node: Any = None
        self._executor: Any = None
        self._publisher: Any = None
        self._twist: Any = None
        self._nav_active_publisher: Any = None
        self._nav_goal_publisher: Any = None
        self._nav_cancel_publisher: Any = None
        self._nav_status = NavigationStatus()
        self._nav_generation = 0
        self._nav_goal_timers: dict[int, threading.Timer] = {}
        self._expired_nav_request_ids: set[str] = set()
        # Generation numbers restart with the Web process. The random session
        # component prevents a delayed status/cancel from a previous process
        # from being mistaken for a new goal with the same generation number.
        self._nav_session = uuid.uuid4().hex
        self._nav_request_id: str | None = None
        self._last_navigation_relay_ready = 0.0

    def start(self) -> None:
        try:
            import rclpy
            from geometry_msgs.msg import Twist
            from nav_msgs.msg import OccupancyGrid, Odometry, Path
            from rclpy.executors import MultiThreadedExecutor
            from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
            from rclpy.time import Time
            from sensor_msgs.msg import BatteryState
            from std_msgs.msg import Bool, String
            from tf2_ros import Buffer, TransformListener
        except ImportError as exc:
            raise RuntimeError("ROS2 Python modules unavailable; use the ROS2 Python 3.10 launcher") from exc
        self._rclpy = rclpy
        self._twist = Twist
        if not rclpy.ok():
            rclpy.init()
        self._node = rclpy.create_node(self.config.node_name)
        self._publisher = self._node.create_publisher(Twist, self.config.cmd_vel_topic, 10)
        self._nav_active_publisher = self._node.create_publisher(String, self.config.navigation_active_topic, 10)
        self._nav_goal_publisher = self._node.create_publisher(String, self.config.navigation_goal_topic, 10)
        self._nav_cancel_publisher = self._node.create_publisher(String, self.config.navigation_cancel_topic, 10)
        self._string = String
        self._ros_time = Time
        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self._node)
        self._node.create_subscription(Odometry, self.config.odom_topic, self._on_odom, qos_profile_sensor_data)
        self._node.create_subscription(BatteryState, self.config.battery_topic, self._on_battery, qos_profile_sensor_data)
        self._node.create_subscription(Bool, self.config.watchdog_status_topic, self._on_watchdog, 10)
        # Relay frames are disposable display data.  Do not allow a delayed
        # map fragment to queue/retransmit in front of navigation control.
        map_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT, durability=DurabilityPolicy.VOLATILE)
        self._node.create_subscription(OccupancyGrid, self.config.map_topic, self._on_map, map_qos)
        self._node.create_subscription(Path, self.config.plan_topic, self._on_path, map_qos)
        self._node.create_subscription(String, self.config.navigation_status_topic, self._on_navigation_status, 10)
        self._node.create_subscription(Bool, self.config.navigation_ready_topic, self._on_navigation_relay_ready, 10)
        self._node.create_timer(0.05, self._publish_velocity)
        # A navigation lease is intentionally low-rate. Motion stays local on
        # the industrial PC; this only permits orderly remote cancellation if
        # the Web server actually disappears.
        self._node.create_timer(0.5, self._publish_navigation_active)
        self._node.create_timer(0.1, self._update_map_pose)
        self._executor = MultiThreadedExecutor(num_threads=self.config.executor_threads)
        self._executor.add_node(self._node)
        self._running = True
        self._thread = threading.Thread(target=self._executor.spin, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._running:
            return
        if self.config.allow_motion_commands:
            try:
                self._cancel_navigation()
            except Exception as exc:
                # Shutdown must still stop the local watchdog signal even if
                # the IPC relay cannot acknowledge cancellation.
                self._node.get_logger().error(f"Nav2 cancellation during shutdown failed: {exc}")
            # Let the small cancel command enter DDS before tearing down the
            # publisher. This is not a navigation wait and never blocks normal
            # request handling.
            time.sleep(0.05)
            with self._lock:
                self._nav_generation += 1
                for timer in self._nav_goal_timers.values():
                    timer.cancel()
                self._nav_goal_timers.clear()
                self._expired_nav_request_ids.clear()
            self.set_velocity(0.0, 0.0)
            self._publish_velocity()
            with self._lock:
                self._nav_status.phase = "idle"
            self._publish_navigation_active()
            with self._lock:
                self._nav_request_id = None
        self._running = False
        self._executor.shutdown(timeout_sec=2.0)
        self._thread.join(timeout=2.0)
        self._node.destroy_node()
        if self._rclpy.ok():
            self._rclpy.shutdown()

    def set_velocity(self, linear: float, angular: float) -> None:
        if not self.config.allow_motion_commands:
            raise MotionControlDisabled("real motion commands are locked by configuration")
        if (abs(linear) > 0.001 or abs(angular) > 0.001) and not self.motion_commands_ready():
            raise MotionControlDisabled("工控机速度看门狗未就绪，请先开启底盘模块")
        with self._lock:
            if (abs(linear) > 0.001 or abs(angular) > 0.001) and self._nav_status.phase in {"sending", "navigating", "canceling"}:
                raise MotionControlDisabled("Nav2 正在导航，请先取消目标再手动驾驶")
            self._velocity = (linear, angular)
            self._last_command = time.monotonic()

    def _publish_velocity(self) -> None:
        if not self.config.allow_motion_commands or self._publisher is None:
            return
        with self._lock:
            linear, angular = self._velocity
            if time.monotonic() - self._last_command > self.config.command_timeout:
                linear, angular = 0.0, 0.0
                self._velocity = (0.0, 0.0)
            message = self._twist()
            message.linear.x = linear
            message.angular.z = angular
        self._publisher.publish(message)

    def _publish_navigation_active(self) -> None:
        with self._lock:
            active = self._nav_status.phase in {"sending", "navigating", "canceling"}
            request_id = self._nav_request_id
        # A request-correlated lease avoids an old ``false`` packet from a
        # previous goal cancelling a newly accepted action on another DDS
        # topic. The IPC relay only acts on a matching request id.
        message = self._string()
        message.data = json.dumps(
            {
                "active": active,
                "request_id": request_id,
                "session": self._nav_session,
            },
            separators=(",", ":"),
        )
        self._nav_active_publisher.publish(message)

    def _on_odom(self, message: Any) -> None:
        q = message.pose.pose.orientation
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        with self._lock:
            self._last_odom = time.monotonic()
            self._state.linear_velocity = float(message.twist.twist.linear.x)
            self._state.angular_velocity = float(message.twist.twist.angular.z)
            self._state.moving = abs(self._state.linear_velocity) > 0.001 or abs(self._state.angular_velocity) > 0.001
            self._state.x = float(message.pose.pose.position.x)
            self._state.y = float(message.pose.pose.position.y)
            self._state.yaw = yaw
            self._state.odom_received = True

    def _on_battery(self, message: Any) -> None:
        with self._lock:
            self._state.battery_voltage = float(message.voltage)
            percentage = float(message.percentage)
            self._state.battery_percentage = percentage if math.isfinite(percentage) else None

    def _on_watchdog(self, message: Any) -> None:
        with self._lock:
            self._last_watchdog = time.monotonic() if bool(message.data) else 0.0

    def _on_navigation_relay_ready(self, message: Any) -> None:
        if bool(message.data):
            with self._lock:
                self._last_navigation_relay_ready = time.monotonic()

    def _on_navigation_status(self, message: Any) -> None:
        """Apply a status emitted by the industrial-PC navigation relay."""
        try:
            payload = json.loads(message.data)
            generation = int(payload["generation"])
            request_id = str(payload["request_id"])
            status = NavigationStatus(
                phase=str(payload["phase"]),
                message=str(payload["message"]),
                x=payload.get("x"),
                y=payload.get("y"),
                yaw=payload.get("yaw"),
            )
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            self._node.get_logger().warning("ignored malformed IPC navigation status")
            return
        with self._lock:
            if generation != self._nav_generation:
                return
            if request_id != self._nav_request_id:
                return
            if request_id in self._expired_nav_request_ids:
                return
            # The relay reports its own "sending" state before Nav2 accepts a
            # goal. Keep the confirmation timer alive until a real outcome or
            # an accepted, navigating state is reported.
            if status.phase != "sending":
                timer = self._nav_goal_timers.pop(generation, None)
                if timer is not None:
                    timer.cancel()
            self._expired_nav_request_ids.discard(request_id)
            self._nav_status = status

    def _update_map_pose(self) -> None:
        try:
            transform = self._tf_buffer.lookup_transform("map", "base_link", self._ros_time())
        except Exception:
            return
        q = transform.transform.rotation
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        with self._lock:
            self._state.map_x = float(transform.transform.translation.x)
            self._state.map_y = float(transform.transform.translation.y)
            self._state.map_yaw = yaw
            self._state.map_pose_received = True
            self._last_map_pose = time.monotonic()

    def _on_map(self, message: Any) -> None:
        now = time.monotonic()
        # The industrial-PC relay has already bounded this display map before
        # it crossed the network. Keep its latest reference and avoid any
        # additional copies on FastAPI's ROS callback path.
        with self._lock:
            cached = self._navigation_grid
            self._last_map = now
            geometry_changed = (
                cached is None
                or cached.frame_id != (message.header.frame_id or "map")
                or cached.width != message.info.width
                or cached.height != message.info.height
                or cached.resolution != message.info.resolution
            )
            if (
                not geometry_changed
                and now - self._last_map_snapshot < self.config.map_snapshot_interval_s
            ):
                return
            path = self._map.path
            revision = self._map.revision + 1
        q = message.info.origin.orientation
        origin_yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        # Goal safety is checked against the raw local map by the industrial
        # relay. The Web server only keeps this bounded display grid.
        source_data: Sequence[int] = message.data
        expected_cells = message.info.width * message.info.height
        if len(source_data) != expected_cells:
            return
        stride = max(1, math.ceil(math.sqrt(expected_cells / self.config.web_map_max_cells)))
        display_width = math.ceil(message.info.width / stride)
        display_height = math.ceil(message.info.height / stride)
        if stride == 1:
            display_data = list(source_data)
        else:
            display_data = []
            for row in range(0, message.info.height, stride):
                row_start = row * message.info.width
                for value in source_data[row_start:row_start + message.info.width:stride]:
                    display_data.append(value - 256 if value > 127 else value)
        # ROS messages are locally typed data. model_construct deliberately
        # avoids Pydantic making a second full-size copy of the display grid.
        snapshot = MapSnapshot.model_construct(
            frame_id=message.header.frame_id or "map",
            width=display_width,
            height=display_height,
            resolution=message.info.resolution * stride,
            origin_x=message.info.origin.position.x,
            origin_y=message.info.origin.position.y,
            origin_yaw=origin_yaw,
            data=display_data,
            path=path,
            revision=revision,
            path_revision=self._map.path_revision,
            updated_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._map = snapshot
            self._navigation_grid = _NavigationGrid(
                frame_id=message.header.frame_id or "map",
                width=message.info.width,
                height=message.info.height,
                resolution=message.info.resolution,
                origin_x=message.info.origin.position.x,
                origin_y=message.info.origin.position.y,
                origin_yaw=origin_yaw,
                data=source_data,
            )
            self._last_map_snapshot = now

    def _on_path(self, message: Any) -> None:
        now = time.monotonic()
        with self._lock:
            if (
                now - self._last_path_snapshot
                < self.config.path_snapshot_interval_s
            ):
                return

        poses = message.poses
        point_count = len(poses)
        maximum = self.config.web_path_max_points
        if point_count <= maximum:
            indices = range(point_count)
        else:
            # Uniform sampling is sufficient for a display-only polyline and
            # preserves both the robot-side and goal-side endpoints. Avoid a
            # full Path -> Pydantic conversion in the ROS callback.
            step = (point_count - 1) / (maximum - 1)
            indices = (round(index * step) for index in range(maximum))
        path = [
            Point2D.model_construct(
                x=float(poses[index].pose.position.x),
                y=float(poses[index].pose.position.y),
            )
            for index in indices
        ]
        with self._lock:
            # Do not mutate a snapshot which might already be held by a map
            # WebSocket response. The grid data itself is immutable after a
            # snapshot is published, so this is intentionally a shallow copy.
            # A second executor thread may have accepted a newer path while
            # this callback was converting points outside the lock.
            if (
                now - self._last_path_snapshot
                < self.config.path_snapshot_interval_s
            ):
                return
            self._map = self._map.model_copy(
                update={
                    "path": path,
                    "path_revision": self._map.path_revision + 1,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            self._last_path_snapshot = now

    def clear_map_cache(self) -> MapSnapshot:
        """Drop only the Web adapter's latest map and path, not SLAM's map."""
        with self._lock:
            self._map = MapSnapshot(
                revision=self._map.revision + 1,
                path_revision=self._map.path_revision + 1,
            )
            self._navigation_grid = None
            self._last_map = 0.0
            self._last_map_snapshot = 0.0
            return self._map.model_copy(deep=True)

    def navigation_status(self) -> NavigationStatus:
        with self._lock:
            return self._nav_status.model_copy(deep=True)

    def navigation_readiness(self) -> tuple[bool, str]:
        if not self.config.allow_motion_commands or not self._running:
            return False, "真机导航未启用"
        chassis = self.get_chassis_state()
        if not chassis.connected:
            return False, "等待底盘里程计上线"
        if not chassis.map_pose_received:
            return False, "等待 map → base_link 定位"
        if not self.motion_commands_ready():
            return False, "等待工控机速度看门狗上线"
        with self._lock:
            grid = self._navigation_grid
            last_map = self._last_map
            manual_velocity = self._velocity
        if abs(manual_velocity[0]) > .001 or abs(manual_velocity[1]) > .001:
            return False, "请先松开手动驾驶控制"
        if grid is None or not grid.data or grid.frame_id != "map":
            return False, "等待工控机地图中继"
        if time.monotonic() - last_map > 30.0:
            return False, "地图已超过 30 秒未更新"
        if abs(grid.origin_yaw) > .001:
            return False, "地图原点带旋转，当前选点暂不支持"
        with self._lock:
            relay_ready_at = self._last_navigation_relay_ready
        if time.monotonic() - relay_ready_at > 2.0:
            return False, "等待工控机本地导航中继与 Nav2 就绪"
        return True, "导航条件已就绪"

    def _expire_navigation_goal_response(self, generation: int, request_id: str) -> None:
        """Unlock manual control if the IPC relay never acknowledges a goal."""
        expired = False
        with self._lock:
            self._nav_goal_timers.pop(generation, None)
            if (
                generation != self._nav_generation
                or request_id != self._nav_request_id
                or self._nav_status.phase != "sending"
            ):
                return
            self._expired_nav_request_ids.add(request_id)
            self._nav_status.phase = "failed"
            self._nav_status.message = "工控机导航中继确认超时，已拒绝本次导航请求"
            expired = True
        if expired:
            payload = self._string()
            payload.data = json.dumps(
                {"generation": generation, "request_id": request_id}, separators=(",", ":")
            )
            self._nav_cancel_publisher.publish(payload)

    def _send_navigation_goal(self, x: float, y: float, yaw: float, frame_id: str) -> NavigationStatus:
        with self._nav_command_lock:
            return self._send_navigation_goal_locked(x, y, yaw, frame_id)

    def _send_navigation_goal_locked(self, x: float, y: float, yaw: float, frame_id: str) -> NavigationStatus:
        ready, reason = self.navigation_readiness()
        if not ready:
            raise MotionControlDisabled(reason)
        with self._lock:
            if self._nav_status.phase in {"sending", "navigating", "canceling"}:
                raise MotionControlDisabled("已有导航目标，请先取消")
            if abs(self._velocity[0]) > .001 or abs(self._velocity[1]) > .001:
                raise MotionControlDisabled("请先释放手动驾驶控制，再设置导航目标")
            self._nav_generation += 1
            generation = self._nav_generation
            request_id = f"{self._nav_session}:{generation}"
            self._nav_request_id = request_id
            self._nav_status = NavigationStatus(
                phase="sending", message="正在发送到工控机本地导航中继", x=x, y=y, yaw=yaw
            )
        payload = self._string()
        payload.data = json.dumps(
            {
                "generation": generation,
                "request_id": request_id,
                "x": x,
                "y": y,
                "yaw": yaw,
                "frame_id": frame_id,
            },
            separators=(",", ":"),
        )
        timer = threading.Timer(
            8.0, self._expire_navigation_goal_response, args=(generation, request_id)
        )
        timer.daemon = True
        with self._lock:
            self._nav_goal_timers[generation] = timer
        timer.start()
        try:
            self._nav_goal_publisher.publish(payload)
        except Exception as exc:
            timer.cancel()
            with self._lock:
                self._nav_goal_timers.pop(generation, None)
                if self._nav_generation == generation and self._nav_request_id == request_id:
                    self._nav_status.phase = "failed"
                    self._nav_status.message = f"工控机导航中继消息发送失败：{exc}"
            raise MotionControlDisabled(f"工控机导航中继消息发送失败：{exc}") from exc
        # The IPC relay validates the original local OccupancyGrid and talks to
        # Nav2 locally. Returning immediately keeps HTTP short and lets status
        # arrive on a small, independent DDS topic.
        return self.navigation_status()

    async def send_navigation_goal(self, x: float, y: float, yaw: float, frame_id: str) -> NavigationStatus:
        return await asyncio.to_thread(self._send_navigation_goal, x, y, yaw, frame_id)

    def _cancel_navigation(self) -> NavigationStatus:
        with self._nav_command_lock:
            return self._cancel_navigation_locked()

    def _cancel_navigation_locked(self) -> NavigationStatus:
        with self._lock:
            if self._nav_status.phase not in {"sending", "navigating", "canceling"}:
                return self._nav_status.model_copy(deep=True)
            generation = self._nav_generation
            request_id = self._nav_request_id
            self._nav_status.phase = "canceling"
            self._nav_status.message = "正在请求工控机取消导航"
        if request_id is None:
            raise MotionControlDisabled("导航请求标识丢失，请使用现场硬件急停")
        payload = self._string()
        payload.data = json.dumps(
            {"generation": generation, "request_id": request_id}, separators=(",", ":")
        )
        self._nav_cancel_publisher.publish(payload)
        return self.navigation_status()

    async def cancel_navigation(self) -> NavigationStatus:
        return await asyncio.to_thread(self._cancel_navigation)

    def get_chassis_state(self) -> ChassisState:
        with self._lock:
            state = self._state.model_copy(deep=True)
            state.connected = self._running and time.monotonic() - self._last_odom < 2.0
            state.map_pose_received = state.map_pose_received and time.monotonic() - self._last_map_pose < 2.0
            return state

    def get_map(self) -> MapSnapshot:
        with self._lock:
            # The map data list is never mutated after publication. Avoiding a
            # deep copy here is essential for large SLAM occupancy grids.
            return self._map.model_copy(deep=False)

    def is_running(self) -> bool:
        return self._running

    def motion_commands_ready(self) -> bool:
        with self._lock:
            return (
                self.config.allow_motion_commands
                and self._running
                and time.monotonic() - self._last_watchdog < self.config.watchdog_timeout
            )
