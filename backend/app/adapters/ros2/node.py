import math
import threading
import time
from datetime import datetime, timezone
from typing import Any

from app.core.config import ROS2Settings
from app.models.chassis import ChassisState
from app.models.visualization import MapSnapshot, Point2D


class MotionControlDisabled(RuntimeError):
    pass


class ROS2NodeAdapter:
    def __init__(self, config: ROS2Settings) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._running = False
        self._last_odom = 0.0
        self._last_command = 0.0
        self._velocity = (0.0, 0.0)
        self._state = ChassisState()
        self._map = MapSnapshot()
        self._thread: threading.Thread | None = None
        self._node: Any = None
        self._executor: Any = None
        self._publisher: Any = None
        self._twist: Any = None

    def start(self) -> None:
        try:
            import rclpy
            from geometry_msgs.msg import Twist
            from nav_msgs.msg import OccupancyGrid, Odometry, Path
            from rclpy.executors import MultiThreadedExecutor
            from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
            from rclpy.time import Time
            from sensor_msgs.msg import BatteryState
            from tf2_ros import Buffer, TransformListener
        except ImportError as exc:
            raise RuntimeError("ROS2 Python modules unavailable; use the ROS2 Python 3.10 launcher") from exc
        self._rclpy = rclpy
        self._twist = Twist
        if not rclpy.ok():
            rclpy.init()
        self._node = rclpy.create_node(self.config.node_name)
        self._publisher = self._node.create_publisher(Twist, self.config.cmd_vel_topic, 10)
        self._ros_time = Time
        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self._node)
        self._node.create_subscription(Odometry, self.config.odom_topic, self._on_odom, qos_profile_sensor_data)
        self._node.create_subscription(BatteryState, self.config.battery_topic, self._on_battery, qos_profile_sensor_data)
        map_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self._node.create_subscription(OccupancyGrid, self.config.map_topic, self._on_map, map_qos)
        self._node.create_subscription(Path, self.config.plan_topic, self._on_path, 10)
        self._node.create_timer(0.05, self._publish_velocity)
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
            self.set_velocity(0.0, 0.0)
            self._publish_velocity()
        self._running = False
        self._executor.shutdown(timeout_sec=2.0)
        self._thread.join(timeout=2.0)
        self._node.destroy_node()
        if self._rclpy.ok():
            self._rclpy.shutdown()

    def set_velocity(self, linear: float, angular: float) -> None:
        if not self.config.allow_motion_commands:
            raise MotionControlDisabled("real motion commands are locked by configuration")
        with self._lock:
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

    def _on_map(self, message: Any) -> None:
        with self._lock:
            self._map = MapSnapshot(
                frame_id=message.header.frame_id or "map", width=message.info.width,
                height=message.info.height, resolution=message.info.resolution,
                origin_x=message.info.origin.position.x, origin_y=message.info.origin.position.y,
                data=list(message.data), path=self._map.path,
                revision=self._map.revision + 1, updated_at=datetime.now(timezone.utc),
            )

    def _on_path(self, message: Any) -> None:
        with self._lock:
            self._map.path = [Point2D(x=p.pose.position.x, y=p.pose.position.y) for p in message.poses]
            self._map.revision += 1
            self._map.updated_at = datetime.now(timezone.utc)

    def get_chassis_state(self) -> ChassisState:
        with self._lock:
            state = self._state.model_copy(deep=True)
            state.connected = self._running and time.monotonic() - self._last_odom < 2.0
            return state

    def get_map(self) -> MapSnapshot:
        with self._lock:
            return self._map.model_copy(deep=True)

    def is_running(self) -> bool:
        return self._running
