# ROS2 接口

已根据工控机 `/home/hzauaiot/songwei/ChassisControl` 与 `start_mapping.sh` 确认：

| 方向 | Topic/TF | 类型 | 用途 |
|---|---|---|---|
| 订阅 | `/odom` | `nav_msgs/msg/Odometry` | 速度与里程计 |
| 订阅 | `/battery_state` | `sensor_msgs/msg/BatteryState` | 电池状态 |
| 订阅 | `/map` | `nav_msgs/msg/OccupancyGrid` | SLAM 地图 |
| 订阅 | `/plan` | `nav_msgs/msg/Path` | Nav2 全局路径 |
| 查询 | `map → base_link` | TF2 | 地图中的机器人位姿 |
| Web 发布 | `/webrobot/cmd_vel` | `geometry_msgs/msg/Twist` | 进入工控机安全看门狗的速度指令 |
| 工控机发布 | `/cmd_vel` | `geometry_msgs/msg/Twist` | 看门狗过滤后发送给底盘驱动 |
| 订阅 | `/webrobot/cmd_vel_watchdog/ready` | `std_msgs/msg/Bool` | 看门狗在线状态 |
| Action 客户端 | `/navigate_to_pose` | `nav2_msgs/action/NavigateToPose` | 地图目标位置和朝向、取消及结果 |
| 订阅 | `/webrobot/nav_cmd_vel` | `geometry_msgs/msg/Twist` | Nav2 经重映射输出的最终导航速度 |
| Web 发布 | `/webrobot/navigation/active` | `std_msgs/msg/Bool` | 导航控制心跳，失联时看门狗归零 |

观测 Topic 和导航 Action 名称可在 `backend/config/config.yaml` 修改；三个安全话题 `/webrobot/cmd_vel`、`/webrobot/navigation/active` 和 `/webrobot/cmd_vel_watchdog/ready` 与工控机脚本配套，启用实车运动时不可单独改名。工控机导航脚本使用 `ROS_DOMAIN_ID=30`，Web 后端必须使用相同 Domain。地图目标需要底盘、速度看门狗、最近 2 秒内的 `map → base_link` 定位、最近 30 秒内的地图和 Nav2 Action Server 均就绪，且目标落在已知空闲栅格。Web 只清自己的地图与路径缓存，不调用 SLAM 清图，也不删除已保存的地图。Nav2 导航过程中，Web 手动驾驶的非零速度指令会被拒绝；取消目标需要 Nav2 确认，不能代替现场硬件急停。
