# RML63 真机机械臂模块

机械臂工作站只面向真机，不提供离线模式。实现参考 `/home/hzauaiot/songwei/grasp_studio` 的 RML63 协议、安全检查、待命位和工具 IO 定义；Web 后端只暴露类型化业务接口，不接受浏览器提交任意 JSON/TCP 报文。

## 通信链路

```text
机械臂页面
  ├─ REST 运动命令 ──► FastAPI ──► RealManArmController ──SSH──► 工控机
  │                                                        └─ enp4s0 ─JSON/TCP─► RML63 :8080
  └─ /ws/robot 状态 ◄─ StateManager ◄─ 控制器状态轮询

夹爪按钮 ──► RealManGripperController ──► RML63 工具端数字 IO
```

Web 服务器只需能免密 SSH 登录工控机；RML63 控制器由工控机专用网口访问。工控机桥接器会检查到控制器的内核路由与源地址，确保链路经过配置网口，不会回退到其他网卡。参数位于 `backend/config/config.yaml`：

```yaml
arm:
  enabled: true
  transport: industrial_pc
  host: 192.168.1.20
  port: 8080
  network_interface: enp4s0
  timeout_s: 2.0
  allow_motion_commands: true
  expected_tool: Arm_Tip
  collision_level: 8
  joint_speed_percent: 5
  pose_speed_percent: 5
  workspace_min_m: [-1.2, -1.2, 0.05]
  workspace_max_m: [1.2, 1.2, 1.0]
  clearance_m: 0.0
  max_pose_segment_m: 0.8
  keepout_enabled: true
  keepout_min_m: [0.0, 0.0, 0.0]
  keepout_max_m: [0.1, 0.1, 0.1]
  standby_joints_deg: [178.0, 37.258, -65.159, 4.531, -107.568, 6.608]

gripper:
  enabled: true
  allow_commands: true
  open_io: 1
  close_io: 2
  active_level: 0
  pulse_s: 1.0
```

后端启动时会通过 SSH 自动把固定功能的 `arm_tcp_bridge.py` 部署到工控机，不需要再手工启动机械臂转发脚本。桥接器只允许连接配置中的机械臂地址与端口，并在建立 TCP 前完成三项检查：工控机存在 `enp4s0`、该网口拥有 IPv4 地址、内核到 `192.168.1.20` 的实际路由使用 `enp4s0`。任一条件不满足都会保持运动锁定，并把具体错误显示在机械臂页面。这里的 `enp4s0` 始终指工控机网卡，与 Web 服务器本机网卡名称无关。

## 控制功能

- 状态读取：六轴角度、TCP 位姿、轨迹状态、工具坐标系和控制器错误；
- 关节运动：一次提交六个目标角，后端从控制器读取实际关节限位并逐轴校验；
- TCP 运动：使用 `movel` 执行直线运动，后端校验 XYZ 工作空间、单段长度，并检查当前位置到目标的工具原点线段是否进入 Base 坐标禁区；
- 待命位：使用与 `grasp_studio` 相同的六轴待命角；
- 夹爪控制：工具端 IO 脉冲完成张开或闭合，完成后自动释放两个输出；
- 组合停止：尝试下发 `set_arm_stop`，并释放夹爪工具 IO。

页面输入的 TCP 平移单位为 mm、旋转单位为 deg，提交接口前转换为 m/rad。关节角始终使用 deg。运动速度采用控制器 `1～100` 的整数百分比，页面为初次联调限制在 `1～20%`。

## 运动解锁条件

只有以下条件全部成立，页面才允许提交运动：

1. 后端处于 `ros2` 真机模式；
2. `arm.enabled` 与 `arm.allow_motion_commands` 均为 `true`；
3. 控制器 TCP 连接正常；
4. 控制器当前没有正在执行的轨迹；
5. 当前工作坐标系为零偏移 `Base`；
6. 当前工具坐标系与 `expected_tool` 一致；
7. 碰撞等级设置成功并从控制器读回确认；
8. 目标未超出控制器关节限位或配置的 XYZ 工作空间；TCP 线段未超过长度上限且未进入配置禁区。

TCP 禁区只检查控制器工具原点的直线路径；关节运动及机械臂连杆、夹爪、相机、支架和线缆不在该几何检查内，因此不构成整臂碰撞规划。真机首次联调应保持低速、空载，现场人员应能随时触发示教器或物理急停。Web“停止全部动作”属于网络控制命令，不能替代安全等级急停。

## 末端视觉

机械臂页面保留大幅末端相机窗口。当前 `visualization.realsense.source` 为 `industrial_pc`：工控机通过现有 FFmpeg 从 D435 的 V4L2 彩色节点 `/dev/video4` 采集，编码为 JPEG 后通过独立 SSH 标准输出通道传给 Web 后端，最终由 `/api/visualization/camera/stream` 向浏览器输出共享 MJPEG。该方案不要求工控机 Python 安装 `pyrealsense2`，也不会把未压缩 YUYV 图像直接发送到局域网。

如 RealSense 改接到 Web 服务器，可将 `source` 设置为 `local`，此时使用后端 `pyrealsense2` 采集；也可以用 `visualization.camera_stream_url` 显式覆盖内置视频源。相机链路与机械臂控制器链路相互独立，且不会在没有真机时生成模拟画面。自动识别、目标选择和视觉伺服尚未接入 Web 控制闭环。
