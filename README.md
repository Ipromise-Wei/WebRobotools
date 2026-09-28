# HZAU@AIOT农业AI机器人协同工作平台

面向移动操作机器人的 Web 一体化控制框架。当前开发版本已支持 ROS2 Humble 实机状态接入、工控机模块管理、安全连续驾驶、RML63 真机机械臂控制，以及 SLAM 地图、Nav2 路径、机器人位姿和摄像头的单页可视化。导航控制、原始地图和完整路径均在工控机本地处理，Web 端只接收有边界的显示遥测数据。

## 当前功能

- FastAPI 后端与 Vue 3 + TypeScript 前端
- 管理员登录、HttpOnly 签名会话、接口限流与控制链路鉴权
- `ChassisController`、`ArmController`、`GripperController` 抽象接口
- Ranger Mini V3 ROS2 控制器与 RML63 真机 JSON/TCP 控制器
- 底盘、机械臂、夹爪 REST API
- 统一 `RobotManager` 与 `StateManager`
- `/ws/robot` 实时状态推送
- Dashboard、底盘、机械臂工作站、夹爪和系统状态页面
- 移动底盘页内嵌工控机中继地图/路径、机器人位姿和摄像头窗口
- 手动建图、Frontier 自动建图、停止建图与地图文件库管理
- 当前 `/map` 的 ROS YAML + PGM 保存，以及 YAML + PGM 地图文件手动导入
- RViz 风格地图交互：缩放、平移、跟随机器人、全屏和图层开关
- ROS2 Humble 局域网只读状态接入（默认 `ROS_DOMAIN_ID=30`）
- RML63 六轴状态、关节运动、TCP 直线运动、停止与工具 IO 夹爪控制

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

## 登录与管理员密码

首次启动后端时，系统会自动创建本机凭据文件 `backend/config/auth.local.json`，并且只在首次启动的终端日志中显示一次初始用户名和随机密码。该文件已加入 `.gitignore`，不会提交到 Git。

需要主动设置或重置密码时，在项目目录执行：

```bash
python3 scripts/set_admin_password.py
```

完成后重启后端。重置密码会同时轮换会话签名密钥，因此重启后原有浏览器会话全部失效。登录成功后，浏览器使用 HttpOnly Cookie 保持会话；REST 控制接口、API 文档、机器人状态 WebSocket 和地图 WebSocket 均受同一登录状态保护。默认会话有效期为 8 小时，连续 5 次登录失败会锁定来源地址 5 分钟，这些参数可在 `backend/config/config.yaml` 的 `auth` 段调整。

局域网 HTTP 部署保持 `cookie_secure: false`。如果后续通过 HTTPS 反向代理对外提供服务，应改为 `cookie_secure: true`。

## 工控机导航与建图

底盘、雷达、定位、建图和 Nav2 由移动底盘页面的模块面板按依赖顺序启动。原有 `/home/hzauaiot/songwei/start_mapping.sh` 不应与 Web 模块面板同时运行，否则可能出现重复节点和直接写入 `/cmd_vel` 的速度发布者。Web 服务器加入同一 ROS2 Domain 后，只接收以下小型状态或有边界的显示数据：

底盘工作站提供地图缓存清除、地图点选/拖动朝向的 Nav2 目标导航与取消。Web 不再启停或重配工控机 `can0`；底盘启动前只读确认它已处于 UP、500000 bit/s。导航速度统一经过工控机速度看门狗；CAN0 前置条件与安全链路说明见 [底盘模块](docs/chassis.md)。

- `/odom`：速度与轮式里程计
- `/battery_state`：电池状态
- `/webrobot/web_map`：由工控机实时通信中继限频、限尺寸后的 SLAM 显示地图
- `/webrobot/web_plan`：由工控机实时通信中继采样后的 Nav2 显示路径
- TF `map → base_link`：机器人在地图中的实时位置

工控机中继在本机读取原始 `/map`、完整 `/plan`，并在本机完成 Nav2 `NavigateToPose` 的目标校验与 Action 调用。因此原始大地图、完整路径和 Nav2 控制循环不再与 Web 视频/浏览器显示争用跨网 DDS 传输。

第一次准备 ROS2 后端：

```bash
./scripts/setup_ros2_backend.sh
```

编辑 `backend/config/config.yaml`，将 `robot.mode` 改为 `ros2`。统一启动脚本会自动选择兼容 ROS2 Humble 的 Python 3.10：

```bash
ROS_DOMAIN_ID=30 ./scripts/start_system.sh
```

当前开发版本支持从移动底盘页面管理工控机运行模块。Web 后端启动后会通过 SSH 自动部署轻量运行代理，清理上一次建图会话，再按依赖顺序启动底盘、雷达、FAST-LIO、点云转激光、通信中继和 Nav2。SLAM Toolbox 与 Frontier 默认关闭，只由建图模式按需启动；“全部停止”仍可中止启动流程并统一回收所有受管进程。

### 手动与自动建图

底盘页面的“建图管理”卡提供两个可取消勾选的互斥模式：

- **手动建图**：在默认运行基线上只增加 SLAM Toolbox；操作者使用页面中的虚拟摇杆或键盘驾驶机器人完成建图。
- **自动建图**：在 SLAM 上增加 `frontier_exploration_ros2`，并通过其控制服务显式开始 Frontier 探索。如果手动建图已经运行，切换自动时只启动 Frontier，当前地图继续使用；切回手动时只停止 Frontier。

两个勾选均关闭时，SLAM 和 Frontier 都不运行；手柄或键盘仍可以驾驶底盘，但不会生成地图。取消建图勾选会停止 Frontier 和 SLAM、清空 Web 地图/路径，但保留底盘、传感器、通信中继和 Nav2。“清显示缓存”仅清除 Web 副本；只要 SLAM 还在运行，它就会再次发布地图。

通信中继和 Nav2 属于默认运行基线。启动 Web 后端时，系统先暂停 Web 地图转发，回收可能残留的 SLAM/Frontier/中继/Nav2，然后以不含 SLAM 的基线方案重启中继和 Nav2，最后再开放地图转发。这保证程序新启动或在无建图模式下刷新页面时不会加载上一次的地图。

自动建图需要工控机已构建 `/home/hzauaiot/songwei/frontier_ws`，并具备 `frontier_exploration_ros2` 和 `nav2_map_server`。开始自动探索前，必须清空作业区域、确认现场物理急停有效，并全程安排现场人员监控。Web 停止、Frontier 停止和速度看门狗均不替代硬件急停。

### 保存与导入地图

“保存当前地图”调用工控机 `nav2_map_server map_saver_cli`，以 transient-local QoS 等待正在发布的 `/map` 最多 25 秒，再保存为标准 ROS 地图 YAML 与 PGM 文件；保存后会确认这两个文件均已生成。导入时须同时选择同一张地图的 `.yaml` 与 `.pgm` 文件；Web 会校验基本格式后保存到工控机：

```text
/home/hzauaiot/.local/share/webrobot/maps
```

导入地图仅加入地图文件库，不会中断 SLAM，也不会自动切换到静态地图定位；使用已保存地图进行 AMCL/定位导航属于单独的运行模式。
启动或停止建图模式不会删除该目录内已保存的 YAML/PGM 文件。

这些模块开关常驻移动底盘页面右侧控制栏。运动区可在虚拟摇杆和键盘模式之间切换：摇杆按住拖动可同时控制线速度和角速度；键盘模式可按住方向键或 `W/A/S/D` 持续驾驶，并可组合前进与转弯。松键、松开摇杆、页面失焦或触控中断即停车；控制区的空格键可请求停止运动或取消导航，但不能替代现场硬件急停。自动建图停止会先向 Frontier 控制服务发送标准 `frontier_exploration_ctl stop`，再停止进程组；即使控制服务无响应，进程回收仍会继续。地图窗口支持鼠标拖拽、滚轮缩放、双击跟随机器人、视图复位、全屏显示、图层显隐以及地图坐标查看。

远程控制要求 Web 服务器已经配置到工控机的免密 SSH 登录。运行接口只接受启动、停止、重启和日志查询，不接受来自浏览器的任意 Shell 命令。手动实车速度首先发布到 `/webrobot/cmd_vel`，再由工控机侧看门狗转发至 `/cmd_vel`；命令超过 0.5 秒未更新时，看门狗会持续向底盘发送零速度。导航目标则由工控机本地中继提交给 Nav2，Nav2 的本地速度同样在 0.5 秒无更新时归零；Web 服务的请求关联控制租约只在持续 10 秒失联后请求取消无人监管的目标，不会因瞬时视频或地图网络抖动造成走停。

## RML63 真机机械臂

机械臂页面只提供真机模式，不提供离线仿真或浏览器端协议透传。默认链路为 Web 后端通过免密 SSH 到工控机 `192.168.123.41`，由后端自动部署的工控机侧固定桥接器校验路由与源地址，并经 `enp4s0` 连接 RML63 `192.168.1.20:8080`。Web 服务器不需要、也不会尝试绑定工控机网卡。

进入机械臂工作站后需要点击“连接机械臂”才会建立上述真机链路。连接操作会先确认工控机桥接器已经部署，再由工控机启动桥接器；服务启动、页面打开和后台状态轮询都不会自动连接控制器。链路异常中断后也必须重新手动连接。断开按钮在机械臂运动期间保持禁用；确认断开时会先释放夹爪 IO，再关闭 SSH/TCP 桥接链路。

真机参数位于 `backend/config/config.yaml` 的 `arm` 与 `gripper` 段。运动前后端会检查运动授权、零偏移 `Base` 工作坐标系、期望工具坐标系、控制器关节限位、配置工作空间，并设置和读回碰撞检测等级。机械臂页支持：

- 实时六轴角度、TCP 位姿、工具坐标系和运动状态显示；
- 六关节目标编辑、低速执行与 `grasp_studio` 待命位；
- TCP 位姿直线运动，页面使用 mm/deg，接口使用 m/rad；
- 工具 IO 夹爪张开、闭合和输出释放；
- 机械臂停止与夹爪 IO 释放的组合停止操作。

从 v0.7.3 起，实时视频可视化完全关闭。`visualization.realsense.enabled` 为 `false`，Web 后端不会启动 RealSense 采集、FFmpeg 编码或 SSH 视频中继，底盘页和机械臂页也不会请求 MJPEG 视频。

Web 停止按钮不是安全等级急停，调试真机时仍必须保证示教器或物理急停可触达。完整接入说明见 [docs/arm.md](docs/arm.md)。

## 测试与构建

```bash
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest
cd frontend && npm run build
```

在安装 ROS 2 Humble 的服务器上，后端应使用 ROS Python 3.10 虚拟环境；首次执行测试时安装开发依赖：

```bash
cd backend
./.venv-ros2/bin/pip install -r requirements-dev.txt
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-ros2/bin/pytest
```

系统边界及接口约定见 [docs/architecture.md](docs/architecture.md) 和 [docs/api.md](docs/api.md)。

每个发布版本都必须同时提交改进日志：简要变化记录在 [CHANGELOG.md](CHANGELOG.md)，完整说明、验证结果与已知边界记录在 [版本日志索引](docs/releases/README.md)。当前优化版本见 [v0.8.0 版本说明](docs/releases/v0.8.0.md)。
