# API 概览

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/auth/status` | 查询当前浏览器登录状态 |
| POST | `/api/auth/login` | 管理员登录并写入 HttpOnly 会话 Cookie |
| POST | `/api/auth/logout` | 清除当前浏览器会话 |
| GET | `/api/system/status` | 完整机器人状态 |
| GET | `/api/chassis/status` | 底盘状态 |
| POST | `/api/chassis/move` | 设置线速度和角速度 |
| POST | `/api/chassis/stop` | 底盘停止 |
| GET | `/api/arm/config` | 真机机械臂地址、运动锁、安全范围与默认速度 |
| GET | `/api/arm/status` | 机械臂状态 |
| GET | `/api/arm/joints` | 六关节角度 |
| GET | `/api/arm/pose` | 末端位姿 |
| POST | `/api/arm/connect` | 手动建立经工控机指定网口的机械臂控制链路 |
| POST | `/api/arm/disconnect` | 释放夹爪 IO 并断开机械臂控制链路 |
| POST | `/api/visualization/map/cache/clear` | 清除 Web 地图与路径缓存，不清 SLAM |
| GET | `/api/visualization/navigation/status` | 读取 Nav2 目标状态 |
| POST | `/api/visualization/navigation/goal` | 向 Nav2 发送地图坐标与朝向 |
| POST | `/api/visualization/navigation/cancel` | 取消当前 Nav2 目标 |
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

导航目标请求体为 `{ "x": 1.2, "y": 0.8, "yaw": 1.57, "frame_id": "map" }`；`x/y` 单位为米，`yaw` 单位为弧度。服务端要求工控机模块面板管理的底盘和 Nav2 均运行；底盘启动时只读验证工控机 `can0` 已是 UP、500000 bit/s。服务端拒绝地图外、未知或非空闲栅格目标，以及定位、速度看门狗、Nav2 Action Server 未就绪的目标；外部自行启动的 Nav2 实例不能用于 Web 地图目标。目标未确认取消或结束前，手动非零速度指令会被拒绝。

除 `/api/auth/*` 与 `/health` 外，全部 REST API 均要求有效登录会话，未登录或会话过期返回 `401`。登录失败次数达到配置上限时返回 `429`。WebSocket `/ws/robot` 与 `/ws/map` 使用同一 HttpOnly Cookie 鉴权，未登录时以 `4401` 关闭连接；会话到期后，现有连接也会在下一次状态更新或心跳时关闭。

WebSocket `/ws/robot` 建立后立即发送 `robot_state` 完整快照。状态版本变化时发送新的完整快照，空闲时发送 `heartbeat`。

WebSocket `/ws/map` 独立推送 `/map` 与 `/plan` 组合快照，避免大尺寸栅格数据阻塞普通状态消息。

浏览器不能向运行管理接口提交命令内容。全部可执行任务及依赖关系均由服务端 `remote_runtime.tasks` 白名单配置决定。关闭仍被其他运行模块依赖的任务，或在依赖尚未运行时启动任务，都会被拒绝。`/api/runtime/start` 会在后台依次启动依赖已经就绪的模块；启动期间可以调用 `/api/runtime/stop` 中止流程并回收已经运行的模块。

机械臂服务启动后默认保持控制链路断开，必须先调用 `/api/arm/connect`。当前真机配置会通过工控机 SSH 启动固定桥接器，由桥接器绑定 `enp4s0` 并连接 `192.168.1.20:8080`；浏览器不能指定主机、端口、网口或原始命令。机械臂关节接口使用角度制，`positions` 必须恰好包含六个值；TCP 位姿接口的 XYZ 使用米、RX/RY/RZ 使用弧度。关节与 TCP 运动请求均可附带 `speed`（`1～100` 整数百分比）。后端只生成固定的 RML63 指令结构，并在运动前执行工具/工作坐标系、碰撞等级、关节限位、工作空间、单段长度和工具原点禁区校验。
