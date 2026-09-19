#!/usr/bin/env python3
"""Industrial-PC velocity watchdog between Web commands and the chassis driver."""

from __future__ import annotations

import argparse
import math
import time
from typing import Any

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Bool


class VelocityWatchdog(Node):
    def __init__(self, input_topic: str, output_topic: str, status_topic: str, timeout: float) -> None:
        super().__init__("webrobot_cmd_vel_watchdog")
        self.timeout = timeout
        self.last_command = 0.0
        self.linear = 0.0
        self.angular = 0.0
        self.publisher = self.create_publisher(Twist, output_topic, 10)
        self.status_publisher = self.create_publisher(Bool, status_topic, 10)
        self.create_subscription(Twist, input_topic, self.command_received, 10)
        self.create_timer(0.05, self.publish_safe_velocity)
        self.get_logger().info(
            f"velocity watchdog ready: {input_topic} -> {output_topic}, timeout={timeout:.2f}s"
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

    def publish_safe_velocity(self) -> None:
        fresh = self.last_command > 0 and time.monotonic() - self.last_command <= self.timeout
        message = Twist()
        if fresh:
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
    parser.add_argument("--status-topic", default="/webrobot/cmd_vel_watchdog/ready")
    parser.add_argument("--timeout", type=float, default=0.5)
    parsed, _ = parser.parse_known_args()
    return parsed


def main() -> None:
    options = arguments()
    rclpy.init()
    node: Any = VelocityWatchdog(
        options.input_topic, options.output_topic, options.status_topic, max(0.1, options.timeout)
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
