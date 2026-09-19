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

工控机控制与可视化链路：

```text
Web 运行面板 ──► Runtime API ──► RemoteRuntimeManager ──SSH──► 工控机运行代理
                                                               ├─ 底盘 / 雷达
                                                               ├─ FAST-LIO / LaserScan
                                                               └─ SLAM Toolbox / Nav2

工控机 ROS2 Topics
  ├─ /odom、/battery_state ──► StateManager ──► /ws/robot
  ├─ /map、/plan ───────────► MapManager ────► /ws/map
  └─ TF map→base_link ──────► 地图机器人位姿
```

地图和摄像头直接嵌入移动底盘页面，不创建单独的可视化页面。

## 分层约束

- API 层只负责输入校验，并调用对应的管理服务。
- 每类设备由独立 Controller 接口描述，Mock 与未来真实实现遵循相同契约。
- `RobotManager` 负责协调设备命令及生成统一状态快照。
- `StateManager` 原子替换状态、维护版本并通知 WebSocket。
- 前端仅理解业务命令和统一状态模型，不出现 Topic、Service 或 Action 名称。
- ROS2 通信实现位于 `app/adapters/ros2`，远程进程编排由 `RemoteRuntimeManager` 和工控机运行代理负责。

## 安全边界

- 浏览器不直接连接工控机 SSH，也不能提交任意远程命令。
- `RemoteRuntimeManager` 只下发服务端配置中的白名单任务。
- 工控机代理为每个任务创建独立进程组，统一处理异常退出、停止和强制回收。
- 实车速度控制要求工控机速度看门狗在线；Web、网络或看门狗任一环节中断后，底盘接收到的速度会在 0.5 秒内归零。

## 并发模型

设备命令由 `RobotManager` 的异步锁串行处理，避免并发命令生成相互覆盖的状态快照。每次命令完成后统一读取三类 Controller 状态并原子发布。
