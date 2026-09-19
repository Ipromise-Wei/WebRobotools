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

Topic 名称可在 `backend/config/config.yaml` 修改。工控机导航脚本使用 `ROS_DOMAIN_ID=30`，Web 后端必须使用相同 Domain。真实运动命令默认关闭。
