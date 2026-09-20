# API 概览

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/system/status` | 完整机器人状态 |
| GET | `/api/chassis/status` | 底盘状态 |
| POST | `/api/chassis/move` | 设置线速度和角速度 |
| POST | `/api/chassis/stop` | 底盘停止 |
| GET | `/api/arm/config` | 真机机械臂地址、运动锁、安全范围与默认速度 |
| GET | `/api/arm/status` | 机械臂状态 |
| GET | `/api/arm/joints` | 六关节角度 |
| GET | `/api/arm/pose` | 末端位姿 |
| POST | `/api/arm/joint` | 单关节控制 |
| POST | `/api/arm/joints` | 六关节控制 |
| POST | `/api/arm/pose` | 末端位姿控制 |
| POST | `/api/arm/stop` | 机械臂停止 |
| POST | `/api/arm/emergency-stop` | 机械臂停止并释放夹爪工具 IO |
| GET | `/api/gripper/status` | 夹爪状态 |
| POST | `/api/gripper/open` | 打开夹爪 |
| POST | `/api/gripper/close` | 关闭夹爪 |
| POST | `/api/gripper/stop` | 停止夹爪 |
| GET | `/api/visualization/config` | 地图、路径、相机及运动锁配置 |
| GET | `/api/visualization/map` | 当前占据栅格与 Nav2 路径 |
| GET | `/api/visualization/camera/status` | RealSense 连接、序列号、帧序号及错误状态 |
| GET | `/api/visualization/camera/stream` | 后端共享的 RealSense 真机 MJPEG 彩色流 |
| GET | `/api/runtime/status` | 工控机连通性和各运行任务状态 |
| POST | `/api/runtime/start` | 按依赖顺序在后台启动全部受管任务 |
| POST | `/api/runtime/stop` | 停止全部受管任务及其子进程 |
| POST | `/api/runtime/tasks/{task_id}/start` | 独立启动指定模块 |
| POST | `/api/runtime/tasks/{task_id}/stop` | 独立停止指定模块 |
| POST | `/api/runtime/tasks/{task_id}/restart` | 独立重启指定模块 |
| GET | `/api/runtime/logs` | 最近运行日志，支持 `lines` 参数 |

WebSocket `/ws/robot` 建立后立即发送 `robot_state` 完整快照。状态版本变化时发送新的完整快照，空闲时发送 `heartbeat`。

WebSocket `/ws/map` 独立推送 `/map` 与 `/plan` 组合快照，避免大尺寸栅格数据阻塞普通状态消息。

浏览器不能向运行管理接口提交命令内容。全部可执行任务及依赖关系均由服务端 `remote_runtime.tasks` 白名单配置决定。关闭仍被其他运行模块依赖的任务，或在依赖尚未运行时启动任务，都会被拒绝。`/api/runtime/start` 会在后台依次启动依赖已经就绪的模块；启动期间可以调用 `/api/runtime/stop` 中止流程并回收已经运行的模块。

机械臂关节接口使用角度制，`positions` 必须恰好包含六个值；TCP 位姿接口的 XYZ 使用米、RX/RY/RZ 使用弧度。关节与 TCP 运动请求均可附带 `speed`（`1～100` 整数百分比）。后端只生成固定的 RML63 指令结构，并在运动前执行工具/工作坐标系、碰撞等级、关节限位、工作空间、单段长度和工具原点禁区校验；浏览器不能透传控制器原始命令。
