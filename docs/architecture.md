# 系统架构

当前阶段的数据流：

```text
Vue 页面
  │ REST command
  ▼
FastAPI Router
  ▼
RobotManager ──序列化命令──► Mock Controller
  │
  ▼
StateManager（唯一对外状态源）
  │ version + snapshot
  ▼
WebSocket /ws/robot
  ▼
Pinia Store ──► 页面实时更新
```

## 分层约束

- API 层只负责输入校验和调用 `RobotManager`。
- 每类设备由独立 Controller 接口描述，Mock 与未来真实实现遵循相同契约。
- `RobotManager` 负责协调设备命令及生成统一状态快照。
- `StateManager` 原子替换状态、维护版本并通知 WebSocket。
- 前端仅理解业务命令和统一状态模型，不出现 Topic、Service 或 Action 名称。
- ROS2 相关实现只能进入 `app/adapters/ros2`，当前仅保留扩展边界。

## 并发模型

设备命令由 `RobotManager` 的异步锁串行处理，避免并发命令生成相互覆盖的状态快照。每次命令完成后统一读取三类 Controller 状态并原子发布。

