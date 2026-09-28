# ROS2 接口

已根据工控机 `/home/hzauaiot/songwei/ChassisControl` 与 `start_mapping.sh` 确认：

| 方向 | Topic/TF | 类型 | 用途 |
|---|---|---|---|
| 订阅 | `/odom` | `nav_msgs/msg/Odometry` | 速度与里程计 |
| 订阅 | `/battery_state` | `sensor_msgs/msg/BatteryState` | 电池状态 |
| 工控机中继订阅 | `/map` | `nav_msgs/msg/OccupancyGrid` | 原始 SLAM 地图；只在工控机本地保留和校验 |
| 工控机中继订阅 | `/plan` | `nav_msgs/msg/Path` | 完整 Nav2 全局路径；只在工控机本地处理 |
| Web 订阅 | `/webrobot/web_map` | `nav_msgs/msg/OccupancyGrid` | 最多 262,144 栅格、2 Hz、Best-Effort 的显示地图 |
| Web 订阅 | `/webrobot/web_plan` | `nav_msgs/msg/Path` | 最多 256 点、0.5 Hz、Best-Effort 的显示路径 |
| 查询 | `map → base_link` | TF2 | 地图中的机器人位姿 |
| Web 发布 | `/webrobot/cmd_vel` | `geometry_msgs/msg/Twist` | 进入工控机安全看门狗的速度指令 |
| 工控机发布 | `/cmd_vel` | `geometry_msgs/msg/Twist` | 看门狗过滤后发送给底盘驱动 |
| 订阅 | `/webrobot/cmd_vel_watchdog/ready` | `std_msgs/msg/Bool` | 看门狗在线状态 |
| Web 发布 | `/webrobot/navigation/goal` | `std_msgs/msg/String` | 带唯一请求标识的目标 JSON |
| Web 发布 | `/webrobot/navigation/cancel` | `std_msgs/msg/String` | 带唯一请求标识的取消 JSON |
| 工控机中继发布 | `/webrobot/navigation/status` | `std_msgs/msg/String` | 目标接收、执行、取消和结果 JSON |
| 工控机中继发布 | `/webrobot/navigation/ready` | `std_msgs/msg/Bool` | 本地 Nav2 Action Server 就绪状态 |
| 工控机中继 Action 客户端 | `/navigate_to_pose` | `nav2_msgs/action/NavigateToPose` | 原始地图校验后的本地目标、取消及结果 |
| 订阅 | `/webrobot/nav_cmd_vel` | `geometry_msgs/msg/Twist` | Nav2 经重映射输出的最终导航速度 |
| Web 发布 | `/webrobot/navigation/active` | `std_msgs/msg/String` | 请求关联的控制租约；中继 10 秒未刷新时请求取消 |

观测 Topic 和导航 Action 名称可在 `backend/config/config.yaml` 修改；控制 Topic `/webrobot/cmd_vel`、`/webrobot/navigation/goal`、`/webrobot/navigation/cancel`、`/webrobot/navigation/status`、`/webrobot/navigation/ready`、`/webrobot/navigation/active` 和 `/webrobot/cmd_vel_watchdog/ready` 与工控机脚本配套，启用实车运动时不可单独改名。工控机导航脚本使用 `ROS_DOMAIN_ID=30`，Web 后端必须使用相同 Domain。地图目标需要底盘、速度看门狗、最近 2 秒内的 `map → base_link` 定位、最近 30 秒内的中继地图和本地 Nav2 Action Server 均就绪，且中继会在原始本地空闲栅格中再次校验目标。Web 只清自己的显示地图与路径缓存，不调用 SLAM 清图，也不删除已保存的地图。Nav2 导航过程中，Web 手动驾驶的非零速度指令会被拒绝；取消目标需要 Nav2 确认，不能代替现场硬件急停。
