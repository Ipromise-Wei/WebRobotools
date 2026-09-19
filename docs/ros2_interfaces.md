# ROS2 接口规划

Phase 0/1 不绑定真实 Topic、Service 或 Action。Phase 2 调研确认设备接口后，所有 rclpy 节点、发布订阅、服务与 Action 客户端应实现于 `backend/app/adapters/ros2/`，Controller 不应向 API 层泄露 ROS2 类型。

