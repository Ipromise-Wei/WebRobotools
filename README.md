# Robot Web Control

面向移动操作机器人的 Web 一体化控制框架。当前 `v0.2.0` 已支持 Mock 调试和 ROS2 Humble 实机状态接入，可在移动底盘页面集中显示控制、SLAM 地图、Nav2 路径、机器人位姿和摄像头窗口。

## 当前功能

- FastAPI 后端与 Vue 3 + TypeScript 前端
- `ChassisController`、`ArmController`、`GripperController` 抽象接口
- Mock Mini V3、Mock RML63 与 Mock Gripper
- 底盘、机械臂、夹爪 REST API
- 统一 `RobotManager` 与 `StateManager`
- `/ws/robot` 实时状态推送
- Dashboard、底盘、机械臂、夹爪和系统状态页面
- 移动底盘页内嵌 `/map`、Nav2 路径、机器人位姿和摄像头窗口
- ROS2 Humble 局域网只读状态接入（默认 `ROS_DOMAIN_ID=30`）

## 本地运行

要求 Python 3.10+ 和 Node.js 18+。

```bash
./scripts/setup.sh
./scripts/start_system.sh
```

也可以分别运行：

```bash
./scripts/start_backend.sh
./scripts/start_frontend.sh
```

打开 <http://localhost:5173>。后端 API 文档位于 <http://localhost:8000/docs>。

## 工控机导航可视化

工控机使用 `/home/hzauaiot/songwei/start_mapping.sh` 启动 Ranger Mini V3、MID-360、FAST-LIO、SLAM Toolbox 和 Nav2。Web 服务器加入同一 ROS2 Domain 后，订阅：

- `/odom`：速度与轮式里程计
- `/battery_state`：电池状态
- `/map`：SLAM Toolbox 二维地图
- `/plan`：Nav2 全局路径
- TF `map → base_link`：机器人在地图中的实时位置

第一次准备 ROS2 后端：

```bash
./scripts/setup_ros2_backend.sh
```

编辑 `backend/config/config.yaml`，将 `robot.mode` 改为 `ros2`，然后启动：

```bash
ROS_DOMAIN_ID=30 ./scripts/start_system_ros2.sh
```

Web 系统不会远程执行 `start_mapping.sh`；导航栈仍由工控机负责启动和停止。由于当前 Ranger 驱动没有 `/cmd_vel` 超时停车保护，配置中的 `allow_motion_commands` 默认保持 `false`。

## 测试与构建

```bash
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest
cd frontend && npm run build
```

系统边界及接口约定见 [docs/architecture.md](docs/architecture.md) 和 [docs/api.md](docs/api.md)。

版本变化见 [CHANGELOG.md](CHANGELOG.md)。
