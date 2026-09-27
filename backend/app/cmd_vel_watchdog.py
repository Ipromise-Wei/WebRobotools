#!/usr/bin/env python3
"""Industrial-PC velocity watchdog between Web commands and the chassis driver."""

from __future__ import annotations

import argparse
import math
import time
from typing import Any

import rclpy
from action_msgs.msg import GoalStatus, GoalStatusArray
from geometry_msgs.msg import Twist
from rclpy.node import Node
from rclpy.qos import qos_profile_action_status_default
from std_msgs.msg import Bool


class VelocityWatchdog(Node):
    def __init__(
        self,
        input_topic: str,
        navigation_topic: str,
        navigation_action: str,
        output_topic: str,
        status_topic: str,
        timeout: float,
    ) -> None:
        super().__init__("webrobot_cmd_vel_watchdog")
        self.timeout = timeout
        self.last_command = 0.0
        self.linear = 0.0
        self.angular = 0.0
        self.nav_last_command = 0.0
        self.nav_linear = 0.0
        self.nav_angular = 0.0
        self.local_navigation_active = False
        self.publisher = self.create_publisher(Twist, output_topic, 10)
        self.status_publisher = self.create_publisher(Bool, status_topic, 10)
        self.create_subscription(Twist, input_topic, self.command_received, 10)
        self.create_subscription(Twist, navigation_topic, self.navigation_received, 10)
        # The Web lease is consumed by telemetry_relay.py, not by this velocity
        # watchdog. Action status and Nav2 velocity are both local to this
        # industrial PC, so normal Ethernet video/map jitter cannot make Nav2
        # alternate between moving and zero velocity.
        self.create_subscription(
            GoalStatusArray,
            f"{navigation_action.rstrip('/')}/_action/status",
            self.navigation_status_received,
            qos_profile_action_status_default,
        )
        self.create_timer(0.05, self.publish_safe_velocity)
        self.get_logger().info(
            f"velocity watchdog ready: {input_topic} -> {output_topic}, "
            f"timeout={timeout:.2f}s, local action={navigation_action}"
        )

    def command_received(self, message: Twist) -> None:
        linear = float(message.linear.x)
        angular = float(message.angular.z)
        if not math.isfinite(linear) or not math.isfinite(angular):
            self.get_logger().warning("discarded non-finite velocity command")
            return
        self.linear = linear
        self.angular = angular
        self.last_command = time.monotonic()

    def navigation_received(self, message: Twist) -> None:
        linear = float(message.linear.x)
        angular = float(message.angular.z)
        if not math.isfinite(linear) or not math.isfinite(angular):
            self.get_logger().warning("discarded non-finite Nav2 velocity")
            return
        self.nav_linear = linear
        self.nav_angular = angular
        self.nav_last_command = time.monotonic()

    def navigation_status_received(self, message: GoalStatusArray) -> None:
        active = any(
            item.status in {
                GoalStatus.STATUS_ACCEPTED,
                GoalStatus.STATUS_EXECUTING,
                GoalStatus.STATUS_CANCELING,
            }
            for item in message.status_list
        )
        if active != self.local_navigation_active:
            self.get_logger().info(
                "local Nav2 action is %s" % ("active" if active else "inactive")
            )
        self.local_navigation_active = active

    def publish_safe_velocity(self) -> None:
        now = time.monotonic()
        # A remote browser/server may be delayed by an image frame or a map
        # packet.  Once it has sent a goal, only the local Nav2 action state
        # and fresh local Nav2 velocity determine motion.  A stale velocity
        # remains fail-safe and is still zeroed after ``timeout``.
        navigation_mode = self.local_navigation_active
        message = Twist()
        if navigation_mode and now - self.nav_last_command <= self.timeout:
            message.linear.x = self.nav_linear
            message.angular.z = self.nav_angular
        elif not navigation_mode and self.last_command > 0 and now - self.last_command <= self.timeout:
            message.linear.x = self.linear
            message.angular.z = self.angular
        self.publisher.publish(message)
        ready = Bool()
        ready.data = True
        self.status_publisher.publish(ready)

    def publish_stop(self) -> None:
        message = Twist()
        for _ in range(3):
            self.publisher.publish(message)
            time.sleep(0.03)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-topic", default="/webrobot/cmd_vel")
    parser.add_argument("--output-topic", default="/cmd_vel")
    parser.add_argument("--navigation-topic", default="/webrobot/nav_cmd_vel")
    parser.add_argument("--navigation-action", default="/navigate_to_pose")
    parser.add_argument("--status-topic", default="/webrobot/cmd_vel_watchdog/ready")
    parser.add_argument("--timeout", type=float, default=0.5)
    parsed, _ = parser.parse_known_args()
    return parsed


def main() -> None:
    options = arguments()
    rclpy.init()
    node: Any = VelocityWatchdog(
        options.input_topic, options.navigation_topic, options.navigation_action,
        options.output_topic, options.status_topic,
        max(0.1, options.timeout),
    )
    try:
        rclpy.spin(node)
    finally:
        node.publish_stop()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
