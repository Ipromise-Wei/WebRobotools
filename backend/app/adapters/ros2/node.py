class ROS2NodeAdapter:
    """Phase-2 extension point for the managed rclpy node."""

    def start(self) -> None:
        raise NotImplementedError("ROS2 support is not enabled in mock mode")

    def stop(self) -> None:
        raise NotImplementedError("ROS2 support is not enabled in mock mode")

