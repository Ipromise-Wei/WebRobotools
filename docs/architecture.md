# 系统架构

当前阶段的数据流：

```text
Vue 页面
  │ HttpOnly 登录会话
  ▼
FastAPI Auth Gate
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
                                                               ├─ SLAM Toolbox / Nav2
                                                               └─ 实时通信中继

工控机 ROS2 Topics
  ├─ /odom、/battery_state ──► StateManager ──► /ws/robot
  ├─ /map、/plan ──本机──► 实时通信中继 ──► /webrobot/web_map、/webrobot/web_plan ──► MapManager ──► /ws/map
  └─ TF map→base_link ──────► 地图机器人位姿

机械臂连接按钮 ──REST──► RobotManager ──► RealManArmController ──SSH stdio──► 工控机桥接器
                                          └► RealManGripperController          └─ enp4s0 ─► RML63 192.168.1.20:8080 / 工具 IO

工控机 RealSense ──V4L2/FFmpeg──► SSH JPEG 管道 ──► Web 单实例帧缓存 ──MJPEG──► 底盘页 / 机械臂页

地图选点/朝向 ──小型 JSON──► 工控机实时通信中继 ──本机 NavigateToPose Action──► Nav2 速度平滑器 ──/webrobot/nav_cmd_vel──► 工控机速度看门狗 ──► /cmd_vel
Web 请求关联租约 ──► 中继（10 秒失联后请求取消；不参与速度循环）
工控机已配置 can0（UP、500000 bit/s） ──只读校验──► Ranger Mini V3 底盘任务
```

地图和摄像头直接嵌入移动底盘页面，不创建单独的可视化页面。

## 分层约束

- API 层只负责输入校验，并调用对应的管理服务。
- 每类设备由独立 Controller 接口描述；机械臂工作站仅解锁 RML63 真机实现。
- `RobotManager` 负责协调设备命令及生成统一状态快照。
- `StateManager` 原子替换状态、维护版本并通知 WebSocket。
- 前端仅理解业务命令和统一状态模型，不出现 Topic、Service 或 Action 名称。
- ROS2 通信实现位于 `app/adapters/ros2`，远程进程编排由 `RemoteRuntimeManager` 和工控机运行代理负责。

## 安全边界

- 浏览器必须先通过管理员登录；REST 控制接口、API 文档和两条 WebSocket 链路统一校验签名会话。
- 密码使用 PBKDF2-SHA256 加盐存储，本机凭据文件不进入 Git；连续失败登录按来源地址临时锁定。
- 浏览器不直接连接工控机 SSH，也不能提交任意远程命令。
- `RemoteRuntimeManager` 只下发服务端配置中的白名单任务。
- 工控机代理为每个任务创建独立进程组，统一处理异常退出、停止和强制回收。
- 手动实车速度控制要求工控机速度看门狗在线；Web 手动命令或本地 Nav2 速度超过 0.5 秒未更新时，底盘接收到的速度会归零。
- 导航目标由工控机本地中继与本地 Nav2 Action 管理。Web 的请求关联控制租约在连续 10 秒未刷新时请求取消无人监管的目标，因此短暂网络抖动不会制造导航走停；该机制不替代物理急停。
- RML63 运动只允许通过类型化接口提交；后端验证 Base 工作系、工具系、碰撞等级、控制器关节限位和 XYZ 工作空间。
- RML63 链路只能由已登录用户在机械臂页面显式连接；后台状态轮询不会自行建立真机连接，断开后也不会被轮询重新打开。
- 工控机桥接器从 `enp4s0` 地址建立机械臂 TCP 连接，并验证到控制器的内核路由确实使用该网口；Web 服务器不会绑定不存在于本机的工控机接口。
- RealSense 默认由工控机从 `/dev/video4` 单实例采集，经 SSH 压缩视频管道交给 Web 后端并向多个浏览器共享；也支持 Web 服务器本机 `pyrealsense2` 模式。缺少设备或依赖时只报告错误，不生成模拟视频。
- Web 停止命令依赖网络和控制器响应，不替代示教器或物理急停，也不构成整臂碰撞规划。

## 并发模型

设备命令由 `RobotManager` 的异步锁串行处理，避免并发命令生成相互覆盖的状态快照。每次命令完成后统一读取三类 Controller 状态并原子发布。
