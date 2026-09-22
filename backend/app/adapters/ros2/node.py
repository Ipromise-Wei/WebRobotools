import asyncio
import math
import threading
import time
from datetime import datetime, timezone
from typing import Any

from app.core.config import ROS2Settings
from app.models.chassis import ChassisState
from app.models.visualization import MapSnapshot, NavigationStatus, Point2D


class MotionControlDisabled(RuntimeError):
    pass


class ROS2NodeAdapter:
    def __init__(self, config: ROS2Settings) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._nav_command_lock = threading.Lock()
        self._running = False
        self._last_odom = 0.0
        self._last_map_pose = 0.0
        self._last_map = 0.0
        self._last_command = 0.0
        self._last_watchdog = 0.0
        self._velocity = (0.0, 0.0)
        self._state = ChassisState()
        self._map = MapSnapshot()
        self._thread: threading.Thread | None = None
        self._node: Any = None
        self._executor: Any = None
        self._publisher: Any = None
        self._twist: Any = None
        self._nav_client: Any = None
        self._nav_active_publisher: Any = None
        self._nav_goal_handle: Any = None
        self._nav_status = NavigationStatus()
        self._nav_generation = 0

    def start(self) -> None:
        try:
            import rclpy
            from geometry_msgs.msg import Twist
            from nav2_msgs.action import NavigateToPose
            from geometry_msgs.msg import PoseStamped
            from rclpy.action import ActionClient
            from action_msgs.msg import GoalStatus
            from nav_msgs.msg import OccupancyGrid, Odometry, Path
            from rclpy.executors import MultiThreadedExecutor
            from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
            from rclpy.time import Time
            from sensor_msgs.msg import BatteryState
            from std_msgs.msg import Bool
            from tf2_ros import Buffer, TransformListener
        except ImportError as exc:
            raise RuntimeError("ROS2 Python modules unavailable; use the ROS2 Python 3.10 launcher") from exc
        self._rclpy = rclpy
        self._twist = Twist
        self._pose_stamped = PoseStamped
        self._nav_action = NavigateToPose
        self._goal_status = GoalStatus
        if not rclpy.ok():
            rclpy.init()
        self._node = rclpy.create_node(self.config.node_name)
        self._publisher = self._node.create_publisher(Twist, self.config.cmd_vel_topic, 10)
        self._nav_client = ActionClient(self._node, NavigateToPose, self.config.navigate_to_pose_action)
        self._nav_active_publisher = self._node.create_publisher(Bool, self.config.navigation_active_topic, 10)
        self._bool = Bool
        self._ros_time = Time
        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self._node)
        self._node.create_subscription(Odometry, self.config.odom_topic, self._on_odom, qos_profile_sensor_data)
        self._node.create_subscription(BatteryState, self.config.battery_topic, self._on_battery, qos_profile_sensor_data)
        self._node.create_subscription(Bool, self.config.watchdog_status_topic, self._on_watchdog, 10)
        map_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self._node.create_subscription(OccupancyGrid, self.config.map_topic, self._on_map, map_qos)
        self._node.create_subscription(Path, self.config.plan_topic, self._on_path, 10)
        self._node.create_timer(0.05, self._publish_velocity)
        self._node.create_timer(0.1, self._publish_navigation_active)
        self._node.create_timer(0.1, self._update_map_pose)
        self._executor = MultiThreadedExecutor(num_threads=2)
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
                # Shutdown must still stop the watchdog heartbeat even if Nav2
                # cannot acknowledge cancellation.
                self._node.get_logger().error(f"Nav2 cancellation during shutdown failed: {exc}")
            self.set_velocity(0.0, 0.0)
            self._publish_velocity()
            with self._lock:
                self._nav_status.phase = "idle"
            self._publish_navigation_active()
        self._running = False
        self._executor.shutdown(timeout_sec=2.0)
        self._thread.join(timeout=2.0)
        self._nav_client.destroy()
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
        message = self._bool()
        message.data = active
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
        q = message.info.origin.orientation
        origin_yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        with self._lock:
            self._last_map = time.monotonic()
            self._map = MapSnapshot(
                frame_id=message.header.frame_id or "map", width=message.info.width,
                height=message.info.height, resolution=message.info.resolution,
                origin_x=message.info.origin.position.x, origin_y=message.info.origin.position.y,
                origin_yaw=origin_yaw,
                data=list(message.data), path=self._map.path,
                revision=self._map.revision + 1, updated_at=datetime.now(timezone.utc),
            )

    def _on_path(self, message: Any) -> None:
        with self._lock:
            self._map.path = [Point2D(x=p.pose.position.x, y=p.pose.position.y) for p in message.poses]
            self._map.revision += 1
            self._map.updated_at = datetime.now(timezone.utc)

    def clear_map_cache(self) -> MapSnapshot:
        """Drop only the Web adapter's latest map and path, not SLAM's map."""
        with self._lock:
            self._map = MapSnapshot(revision=self._map.revision + 1)
            self._last_map = 0.0
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
            grid = self._map
            last_map = self._last_map
            manual_velocity = self._velocity
        if abs(manual_velocity[0]) > .001 or abs(manual_velocity[1]) > .001:
            return False, "请先松开手动驾驶控制"
        if not grid.data or grid.frame_id != "map":
            return False, "等待 map 坐标系的 SLAM 地图"
        if time.monotonic() - last_map > 30.0:
            return False, "地图已超过 30 秒未更新"
        if abs(grid.origin_yaw) > .001:
            return False, "地图原点带旋转，当前选点暂不支持"
        if not self._nav_client.server_is_ready():
            return False, "等待 Nav2 导航模块就绪"
        return True, "导航条件已就绪"

    def _goal_result(self, future: Any, generation: int) -> None:
        try:
            result = future.result()
            succeeded = result.status == self._goal_status.STATUS_SUCCEEDED
            phase = "succeeded" if succeeded else "canceled" if result.status == self._goal_status.STATUS_CANCELED else "failed"
            message = "已到达目标" if succeeded else "导航已取消" if phase == "canceled" else f"导航失败，状态码 {result.status}"
        except Exception as exc:
            phase, message = "failed", f"导航结果异常：{exc}"
        with self._lock:
            if generation == self._nav_generation:
                self._nav_goal_handle = None
                self._nav_status.phase = phase
                self._nav_status.message = message

    def _send_navigation_goal(self, x: float, y: float, yaw: float, frame_id: str) -> NavigationStatus:
        with self._nav_command_lock:
            return self._send_navigation_goal_locked(x, y, yaw, frame_id)

    def _send_navigation_goal_locked(self, x: float, y: float, yaw: float, frame_id: str) -> NavigationStatus:
        ready, reason = self.navigation_readiness()
        if not ready:
            raise MotionControlDisabled(reason)
        with self._lock:
            grid = self._map
            if self._nav_status.phase in {"sending", "navigating", "canceling"}:
                raise MotionControlDisabled("已有导航目标，请先取消")
            if not grid.data or grid.frame_id != frame_id or grid.resolution <= 0:
                raise MotionControlDisabled("没有与目标坐标系匹配的地图")
            if time.monotonic() - self._last_map > 30.0:
                raise MotionControlDisabled("地图数据已超过 30 秒未更新，禁止发送导航目标")
            if abs(self._velocity[0]) > .001 or abs(self._velocity[1]) > .001:
                raise MotionControlDisabled("请先释放手动驾驶控制，再设置导航目标")
            if abs(grid.origin_yaw) > .001:
                raise MotionControlDisabled("地图原点存在旋转，当前 Web 地图暂不支持安全选点")
            column = math.floor((x - grid.origin_x) / grid.resolution)
            row = math.floor((y - grid.origin_y) / grid.resolution)
            if not 0 <= column < grid.width or not 0 <= row < grid.height:
                raise MotionControlDisabled("导航目标在地图范围外")
            if grid.data[row * grid.width + column] != 0:
                raise MotionControlDisabled("目标点不是已知空闲区域")
        if not self._nav_client.server_is_ready():
            raise MotionControlDisabled("Nav2 NavigateToPose action 未就绪，请先开启导航模块")
        goal = self._nav_action.Goal()
        goal.pose = self._pose_stamped()
        goal.pose.header.frame_id = frame_id
        goal.pose.header.stamp = self._node.get_clock().now().to_msg()
        goal.pose.pose.position.x = x
        goal.pose.pose.position.y = y
        goal.pose.pose.orientation.z = math.sin(yaw / 2)
        goal.pose.pose.orientation.w = math.cos(yaw / 2)
        with self._lock:
            self._nav_generation += 1
            generation = self._nav_generation
            self._nav_status = NavigationStatus(phase="sending", message="等待 Nav2 接收目标", x=x, y=y, yaw=yaw)
        try:
            response = self._nav_client.send_goal_async(goal)
        except Exception as exc:
            with self._lock:
                self._nav_status.phase = "failed"
                self._nav_status.message = str(exc)
            raise MotionControlDisabled(str(exc)) from exc
        accepted = threading.Event()
        response.add_done_callback(lambda _: accepted.set())
        if not accepted.wait(8):
            # If Nav2 accepts after the HTTP timeout, cancel that late goal.
            with self._lock:
                self._nav_status.phase = "canceling"
                self._nav_status.message = "目标确认超时，正在请求取消；取消确认前禁止手动驾驶"
            def cancel_late(future: Any) -> None:
                try:
                    late_handle = future.result()
                    if late_handle.accepted:
                        with self._lock:
                            self._nav_goal_handle = late_handle
                        late_handle.get_result_async().add_done_callback(lambda result: self._goal_result(result, generation))
                        late_handle.cancel_goal_async()
                    else:
                        with self._lock:
                            self._nav_status.phase = "failed"
                            self._nav_status.message = "Nav2 拒绝超时目标"
                except Exception:
                    pass
            response.add_done_callback(cancel_late)
            raise MotionControlDisabled("等待 Nav2 确认目标超时")
        try:
            handle = response.result()
            if not handle.accepted:
                raise MotionControlDisabled("Nav2 拒绝导航目标")
            with self._lock:
                self._nav_goal_handle = handle
                self._nav_status.phase = "navigating"
                self._nav_status.message = "导航中"
            handle.get_result_async().add_done_callback(lambda future: self._goal_result(future, generation))
            return self.navigation_status()
        except Exception as exc:
            with self._lock:
                self._nav_status.phase = "failed"
                self._nav_status.message = str(exc)
            raise MotionControlDisabled(str(exc)) from exc

    async def send_navigation_goal(self, x: float, y: float, yaw: float, frame_id: str) -> NavigationStatus:
        return await asyncio.to_thread(self._send_navigation_goal, x, y, yaw, frame_id)

    def _cancel_navigation(self) -> NavigationStatus:
        with self._nav_command_lock:
            return self._cancel_navigation_locked()

    def _cancel_navigation_locked(self) -> NavigationStatus:
        with self._lock:
            handle = self._nav_goal_handle
            if handle is None:
                if self._nav_status.phase in {"sending", "canceling"}:
                    raise MotionControlDisabled("Nav2 目标确认或取消尚未完成，请使用现场硬件急停")
                return self._nav_status.model_copy(deep=True)
            self._nav_status.message = "正在取消导航"
        response = handle.cancel_goal_async()
        completed = threading.Event()
        response.add_done_callback(lambda _: completed.set())
        if not completed.wait(5):
            raise MotionControlDisabled("Nav2 取消目标超时，请使用现场急停")
        with self._lock:
            if self._nav_goal_handle is not handle:
                return self._nav_status.model_copy(deep=True)
        try:
            accepted_cancel = bool(response.result().goals_canceling)
        except Exception as exc:
            raise MotionControlDisabled(f"Nav2 取消目标异常：{exc}；请使用现场急停") from exc
        if not accepted_cancel:
            raise MotionControlDisabled("Nav2 未确认取消目标，请使用现场急停")
        with self._lock:
            if self._nav_goal_handle is not handle:
                return self._nav_status.model_copy(deep=True)
            self._nav_status.phase = "canceling"
            self._nav_status.message = "Nav2 已接收取消请求，等待目标结束"
            return self._nav_status.model_copy(deep=True)

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
            return self._map.model_copy(deep=True)

    def is_running(self) -> bool:
        return self._running

    def motion_commands_ready(self) -> bool:
        with self._lock:
            return (
                self.config.allow_motion_commands
                and self._running
                and time.monotonic() - self._last_watchdog < self.config.watchdog_timeout
            )
