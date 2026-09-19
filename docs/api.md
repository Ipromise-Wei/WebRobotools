# API 概览

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/system/status` | 完整机器人状态 |
| GET | `/api/chassis/status` | 底盘状态 |
| POST | `/api/chassis/move` | 设置线速度和角速度 |
| POST | `/api/chassis/stop` | 底盘停止 |
| GET | `/api/arm/status` | 机械臂状态 |
| GET | `/api/arm/joints` | 六关节角度 |
| GET | `/api/arm/pose` | 末端位姿 |
| POST | `/api/arm/joint` | 单关节控制 |
| POST | `/api/arm/joints` | 六关节控制 |
| POST | `/api/arm/pose` | 末端位姿控制 |
| POST | `/api/arm/stop` | 机械臂停止 |
| GET | `/api/gripper/status` | 夹爪状态 |
| POST | `/api/gripper/open` | 打开夹爪 |
| POST | `/api/gripper/close` | 关闭夹爪 |
| POST | `/api/gripper/stop` | 停止夹爪 |

WebSocket `/ws/robot` 建立后立即发送 `robot_state` 完整快照。状态版本变化时发送新的完整快照，空闲时发送 `heartbeat`。

