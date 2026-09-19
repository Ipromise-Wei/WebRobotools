# HZAU@AIOT农业AI机器人协同工作平台

面向移动操作机器人的 Web 一体化控制框架。当前 `v0.3.0` 已支持 ROS2 Humble 实机状态接入、工控机模块管理、安全连续驾驶，以及 SLAM 地图、Nav2 路径、机器人位姿和摄像头的单页可视化。

## 当前功能

- FastAPI 后端与 Vue 3 + TypeScript 前端
- `ChassisController`、`ArmController`、`GripperController` 抽象接口
- Mock Mini V3、Mock RML63 与 Mock Gripper
- 底盘、机械臂、夹爪 REST API
- 统一 `RobotManager` 与 `StateManager`
- `/ws/robot` 实时状态推送
- Dashboard、底盘、机械臂、夹爪和系统状态页面
- 移动底盘页内嵌 `/map`、Nav2 路径、机器人位姿和摄像头窗口
- RViz 风格地图交互：缩放、平移、跟随机器人、全屏和图层开关
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

编辑 `backend/config/config.yaml`，将 `robot.mode` 改为 `ros2`。统一启动脚本会自动选择兼容 ROS2 Humble 的 Python 3.10：

```bash
ROS_DOMAIN_ID=30 ./scripts/start_system.sh
```

当前开发版本支持从移动底盘页面管理工控机运行模块。后端会通过 SSH 自动部署轻量运行代理，底盘、雷达、FAST-LIO、点云转激光、SLAM Toolbox 和 Nav2 均有独立开关、进程状态和日志；既可逐项手动开启，也可用“一键全启”按依赖顺序后台启动，并使用“全部停止”中止启动流程或统一回收，不再依赖人工执行 `start_mapping.sh`。

这些模块开关常驻移动底盘页面右侧控制栏。运动区可在虚拟摇杆和键盘模式之间切换：摇杆按住拖动可同时控制线速度和角速度；键盘模式可按住方向键或 `W/A/S/D` 持续驾驶，并可组合前进与转弯。松键、松开摇杆、页面失焦或触控中断即停车，空格键可急停。地图窗口支持鼠标拖拽、滚轮缩放、双击跟随机器人、视图复位、全屏显示、图层显隐以及地图坐标查看。

远程控制要求 Web 服务器已经配置到工控机的免密 SSH 登录。运行接口只接受启动、停止、重启和日志查询，不接受来自浏览器的任意 Shell 命令。实车速度首先发布到 `/webrobot/cmd_vel`，再由工控机侧看门狗转发至 `/cmd_vel`；命令超过 0.5 秒未更新时，看门狗会持续向底盘发送零速度。

## 测试与构建

```bash
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest
cd frontend && npm run build
```

系统边界及接口约定见 [docs/architecture.md](docs/architecture.md) 和 [docs/api.md](docs/api.md)。

版本变化见 [CHANGELOG.md](CHANGELOG.md)。
