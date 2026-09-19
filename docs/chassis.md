# 底盘模块

当前由 `MockChassis` 实现线速度、角速度、停止与连接状态。速度输入范围由 API 模型校验：线速度 `[-1, 1]`，角速度 `[-2, 2]`。

ROS2 模式使用 `MiniV3ChassisController`，Topic 均由 YAML 配置。Web 速度命令发布到 `/webrobot/cmd_vel`，只有工控机侧速度看门狗持续在线时才允许控制。看门狗负责转发到 `/cmd_vel`，并在命令超时后持续发送零速度。
