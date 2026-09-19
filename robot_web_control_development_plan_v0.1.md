# 移动操作机器人 Web 一体化控制系统开发框架

> 文档版本：V0.1  
> 文档性质：第一版总体开发框架  
> 当前阶段：系统架构设计  
> 目标对象：后续交由 Codex 按阶段持续开发  
> 核心原则：先搭框架，再接设备；先统一抽象，再实现具体控制；不直接把现有终端命令机械式搬到 Web 页面中。

---

## 1. 项目名称

**基于 ROS2 的移动操作机器人 Web 一体化控制与可视化系统**

---

## 2. 项目背景

当前机器人平台主要由以下设备组成：

- 松灵 Mini V3 移动底盘
- 睿尔曼 RML63 六自由度机械臂
- 自治夹爪
- Ubuntu 主控计算机
- ROS2 机器人软件环境

项目目标不是简单地把目前在终端中执行的 ROS2 命令包装成几个网页按钮，而是重新构建一套面向实际使用者的统一机器人控制系统。

该系统最终应当实现：

1. 用户通过浏览器访问机器人控制平台；
2. 在同一界面中控制底盘、机械臂和夹爪；
3. 实时查看各设备状态；
4. 将 ROS2 作为底层机器人通信基础设施，而不是直接暴露给普通用户；
5. 为后续相机、导航、视觉识别、自主抓取、任务编排等功能提供扩展基础。

---

## 3. 总体开发目标

系统最终形成如下逻辑：

```text
用户
 ↓
Web 前端
 ↓
Web 后端
 ↓
机器人统一控制层
 ↓
ROS2 / SDK / 通信适配层
 ↓
Mini V3 / RML63 / 夹爪
```

Web 页面负责：

- 控制操作
- 状态展示
- 参数输入
- 报警提示
- 可视化
- 任务交互

后端负责：

- 机器人状态管理
- 控制命令校验
- 设备统一抽象
- ROS2 通信
- WebSocket 实时数据推送
- 安全控制
- 日志记录

ROS2 负责：

- 底层消息通信
- 机器人节点管理
- Topic / Service / Action
- TF
- JointState
- 后续导航与运动规划

---

## 4. 第一版开发原则

### 4.1 不直接绑定终端命令

第一阶段禁止采用如下思路：

```text
网页按钮
  ↓
后台执行 shell
  ↓
ros2 topic pub ...
```

这种方式只能作为临时调试手段，不作为系统正式架构。

正式架构应采用：

```text
网页控制
  ↓
后端 API
  ↓
设备控制器
  ↓
ROS2 接口
  ↓
设备
```

---

### 4.2 前端不直接理解 ROS2

前端只需要知道：

```text
move_forward()
move_backward()
stop()

move_joint()
move_pose()

gripper_open()
gripper_close()
```

前端不需要知道：

```text
/cmd_vel

sensor_msgs/msg/JointState

geometry_msgs/msg/Twist

具体 Service 名称

具体 Action 名称
```

ROS2 细节统一封装在后端。

---

### 4.3 设备解耦

底盘、机械臂、夹爪分别设计独立控制模块：

```text
ChassisController

ArmController

GripperController
```

禁止把三类设备控制逻辑混在一个大文件中。

---

### 4.4 先定义统一接口，再接真实设备

例如先定义：

```python
class ChassisController:
    def move(self, linear, angular):
        pass

    def stop(self):
        pass

    def get_state(self):
        pass
```

然后再实现：

```text
MiniV3ChassisController
```

这样以后如果更换底盘，不需要重写 Web 系统。

机械臂和夹爪同理。

---

## 5. 系统总体架构

```text
┌──────────────────────────────────────────────┐
│                 Web Browser                  │
│                                              │
│ Dashboard / Chassis / Arm / Gripper / Logs │
└──────────────────────┬───────────────────────┘
                       │
              HTTP / WebSocket
                       │
┌──────────────────────▼───────────────────────┐
│                 Web Backend                  │
│                                              │
│ REST API                                     │
│ WebSocket                                    │
│ State Manager                                │
│ Command Validator                            │
│ Robot Manager                                │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│              Robot Control Layer             │
│                                              │
│ ChassisController                            │
│ ArmController                                │
│ GripperController                            │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│              Communication Layer             │
│                                              │
│ ROS2 Adapter                                 │
│ SDK Adapter                                  │
│ TCP Adapter                                  │
│ Serial / CAN Adapter                         │
└──────────────────────┬───────────────────────┘
                       │
      ┌────────────────┼────────────────┐
      │                │                │
┌─────▼─────┐    ┌─────▼─────┐    ┌─────▼─────┐
│ Mini V3   │    │  RML63    │    │  Gripper  │
└───────────┘    └───────────┘    └───────────┘
```

---

## 6. 推荐技术栈

### 6.1 后端

建议：

```text
Python
FastAPI
WebSocket
rclpy
Pydantic
YAML
```

原因：

- ROS2 Python 接口成熟；
- FastAPI 适合快速开发机器人控制 API；
- WebSocket 适合实时状态推送；
- Python 方便后续集成视觉与算法模块。

---

### 6.2 前端

建议：

```text
Vue 3
TypeScript
Vite
Pinia
Axios
WebSocket
```

第一阶段不需要追求复杂 UI。

重点首先是：

- 架构清晰；
- 功能稳定；
- 数据流正确；
- 设备状态可靠。

---

## 7. 推荐项目目录

第一版项目建议采用：

```text
robot_web_control/

├── README.md
├── DEVELOPMENT_PLAN.md
├── .gitignore
│
├── backend/
│   ├── requirements.txt
│   ├── main.py
│   │
│   ├── app/
│   │   ├── api/
│   │   │   ├── system.py
│   │   │   ├── chassis.py
│   │   │   ├── arm.py
│   │   │   └── gripper.py
│   │   │
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── logger.py
│   │   │   ├── state_manager.py
│   │   │   └── robot_manager.py
│   │   │
│   │   ├── controllers/
│   │   │   ├── base/
│   │   │   │   ├── chassis_base.py
│   │   │   │   ├── arm_base.py
│   │   │   │   └── gripper_base.py
│   │   │   │
│   │   │   ├── chassis/
│   │   │   │   └── mini_v3.py
│   │   │   │
│   │   │   ├── arm/
│   │   │   │   └── rml63.py
│   │   │   │
│   │   │   └── gripper/
│   │   │       └── gripper.py
│   │   │
│   │   ├── adapters/
│   │   │   ├── ros2/
│   │   │   │   ├── node.py
│   │   │   │   ├── publisher.py
│   │   │   │   ├── subscriber.py
│   │   │   │   ├── service.py
│   │   │   │   └── action.py
│   │   │   │
│   │   │   └── device/
│   │   │
│   │   ├── models/
│   │   │   ├── chassis.py
│   │   │   ├── arm.py
│   │   │   ├── gripper.py
│   │   │   └── system.py
│   │   │
│   │   └── websocket/
│   │       └── manager.py
│   │
│   └── config/
│       └── config.yaml
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   │
│   └── src/
│       ├── main.ts
│       ├── App.vue
│       │
│       ├── views/
│       │   ├── Dashboard.vue
│       │   ├── Chassis.vue
│       │   ├── Arm.vue
│       │   ├── Gripper.vue
│       │   └── System.vue
│       │
│       ├── components/
│       │   ├── DeviceStatus.vue
│       │   ├── ChassisControl.vue
│       │   ├── ArmControl.vue
│       │   ├── GripperControl.vue
│       │   └── SystemLog.vue
│       │
│       ├── api/
│       │   └── robot.ts
│       │
│       ├── stores/
│       │   └── robot.ts
│       │
│       └── websocket/
│           └── robotSocket.ts
│
├── scripts/
│   ├── start_backend.sh
│   ├── start_frontend.sh
│   └── start_system.sh
│
└── docs/
    ├── architecture.md
    ├── ros2_interfaces.md
    ├── chassis.md
    ├── arm.md
    └── gripper.md
```

该目录目前只是第一版框架。

后续可根据实际代码调整，但不能破坏模块分层原则。

---

## 8. 后端核心模块

### 8.1 RobotManager

RobotManager 是整个后端机器人控制核心。

负责统一管理：

```text
ChassisController
ArmController
GripperController
```

外部 API 不直接调用 ROS2。

统一调用：

```text
RobotManager
```

例如：

```text
POST /api/chassis/move
        ↓
RobotManager
        ↓
ChassisController
        ↓
ROS2 Adapter
```

---

## 9. Controller 层

### 9.1 ChassisController

负责：

- 底盘运动
- 底盘停止
- 底盘速度设置
- 底盘状态读取

统一接口：

```text
move(linear, angular)

stop()

get_state()

is_connected()
```

---

### 9.2 ArmController

负责：

- 关节运动
- 笛卡尔空间运动
- 停止运动
- 获取关节角度
- 获取末端位姿
- 获取机械臂状态

接口初步定义：

```text
move_joint()

move_joints()

move_pose()

stop()

get_joint_state()

get_pose()

get_state()

is_connected()
```

---

### 9.3 GripperController

负责：

- 打开
- 关闭
- 停止
- 设置开度
- 设置夹持力
- 获取状态

接口：

```text
open()

close()

stop()

set_position()

set_force()

get_state()

is_connected()
```

具体能力根据夹爪真实硬件确定。

---

## 10. StateManager

机器人系统不能只有“发送命令”，还必须统一维护机器人状态。

StateManager 负责维护：

```text
SystemState

ChassisState

ArmState

GripperState
```

例如：

```json
{
  "system": {
    "ros2": true,
    "backend": true
  },
  "chassis": {
    "connected": true,
    "linear_velocity": 0.0,
    "angular_velocity": 0.0
  },
  "arm": {
    "connected": true,
    "moving": false
  },
  "gripper": {
    "connected": true,
    "opened": true
  }
}
```

前端不需要直接订阅 ROS2。

后端统一将状态通过 WebSocket 推送给前端。

---

## 11. WebSocket 设计

WebSocket 主要负责实时状态。

推荐：

```text
/ws/robot
```

后端持续推送：

```text
robot_state
device_status
motion_state
system_log
warning
error
```

例如：

```json
{
  "type": "robot_state",
  "data": {
    "chassis": {},
    "arm": {},
    "gripper": {}
  }
}
```

第一阶段不需要设计复杂协议。

先保证：

```text
WebSocket 建立

↓

后端状态更新

↓

前端实时显示
```

---

## 12. REST API 第一版

### 系统

```text
GET /api/system/status
```

---

### 底盘

```text
GET  /api/chassis/status

POST /api/chassis/move

POST /api/chassis/stop
```

---

### 机械臂

```text
GET  /api/arm/status

GET  /api/arm/joints

GET  /api/arm/pose

POST /api/arm/joint

POST /api/arm/joints

POST /api/arm/pose

POST /api/arm/stop
```

---

### 夹爪

```text
GET  /api/gripper/status

POST /api/gripper/open

POST /api/gripper/close

POST /api/gripper/stop
```

这些接口目前只是系统层统一抽象。

后续根据真实设备能力继续调整。

---

## 13. 前端第一版页面

### 13.1 Dashboard

展示：

```text
系统状态

Mini V3 状态

RML63 状态

夹爪状态

ROS2 状态
```

---

### 13.2 Chassis

包含：

```text
前进
后退
左转
右转
停止

线速度
角速度
```

以及：

```text
当前速度
连接状态
```

---

### 13.3 Arm

显示：

```text
J1
J2
J3
J4
J5
J6
```

以及：

```text
X
Y
Z
RX
RY
RZ
```

控制区域第一版只搭 UI 和接口结构。

具体运动方式在设备接口明确之后再实现。

---

### 13.4 Gripper

第一版：

```text
打开

关闭

停止
```

以及夹爪状态。

---

## 14. 第一阶段暂时不实现

第一阶段禁止过早加入：

- SLAM
- Navigation2
- MoveIt2
- YOLO
- 深度相机
- 自动抓取
- 轨迹规划
- 任务编排
- 用户权限系统
- 数据库
- 云端控制
- 复杂 3D 场景

这些功能以后都可以增加。

当前阶段重点只有：

> 搭建一个结构正确、能够持续扩展的机器人 Web 控制基础框架。

---

## 15. 第一阶段开发路线

### Phase 0：项目骨架

目标：

```text
创建 backend

创建 frontend

创建配置系统

创建日志系统

创建 Controller 抽象类

创建 RobotManager

创建 StateManager
```

这个阶段：

**不连接真实机器人。**

---

### Phase 1：Mock Robot

开发虚拟机器人接口：

```text
MockChassis

MockArm

MockGripper
```

例如：

点击网页：

```text
前进
```

MockChassis 返回：

```text
linear_velocity = 0.3
```

这样可以在完全不连接设备的情况下验证：

```text
前端
 ↓
API
 ↓
Controller
 ↓
StateManager
 ↓
WebSocket
 ↓
前端
```

整个软件链路。

这一阶段非常重要。

---

### Phase 2：ROS2 基础层

开始建立：

```text
ROS2Node

Publisher

Subscriber

ServiceClient

ActionClient
```

但暂时不绑定具体机器人。

目标：

验证 Web 后端能够正常运行 ROS2 节点。

---

### Phase 3：Mini V3 接入

首先接底盘。

原因：

- 控制逻辑简单；
- 容易测试；
- 风险较低；
- 可以快速验证 Web → ROS2 → 实体设备链路。

实现：

```text
MiniV3Controller
```

完成：

```text
前进
后退
转向
停止
状态读取
```

---

### Phase 4：RML63 接入

在底盘链路稳定后再接机械臂。

首先实现：

```text
读取关节状态

读取末端位姿

停止机械臂
```

之后再增加：

```text
单关节控制

多关节控制

末端位姿控制
```

不要一开始就实现复杂轨迹规划。

---

### Phase 5：夹爪接入

实现：

```text
连接

打开

关闭

停止

状态读取
```

之后根据硬件支持情况增加：

```text
位置

速度

夹持力
```

---

### Phase 6：统一状态页面

实现：

```text
Mini V3      Online

RML63        Online

Gripper      Online

ROS2         Running

Backend      Running
```

同时增加：

```text
Warning

Error

Emergency
```

---

### Phase 7：系统联调

实现：

```text
底盘控制

机械臂控制

夹爪控制
```

在一个 Web 系统中稳定运行。

---

## 16. Codex 第一阶段开发要求

Codex 第一轮只负责搭建基础工程。

### 必须完成

```text
backend 基础目录

frontend 基础目录

FastAPI

Vue3

Controller 抽象类

RobotManager

StateManager

MockChassis

MockArm

MockGripper

基础 REST API

WebSocket

Dashboard 页面

底盘页面

机械臂页面

夹爪页面
```

---

### 第一轮禁止

不得：

```text
直接调用 ros2 topic pub

直接执行 shell 控制机器人

写死 Topic

写死 Service

写死 Action

大量编写真实设备控制逻辑
```

第一轮只验证系统软件架构。

---

## 17. Codex 开发规则

Codex 开始开发前：

1. 完整阅读本文件；
2. 首先搭建目录结构；
3. 不直接连接真实机器人；
4. 使用 Mock Controller 验证架构；
5. 每个设备必须独立 Controller；
6. 前端不得包含 ROS2 Topic 名称；
7. API 层不得直接操作 ROS2；
8. ROS2 代码必须放在 Adapter 层；
9. 所有状态统一通过 StateManager 管理；
10. 所有实时状态通过 WebSocket 推送。

---

## 18. 第一轮验收标准

第一轮完成后启动系统。

浏览器打开：

```text
http://<robot-ip>:<port>
```

可以进入：

```text
Dashboard

Chassis

Arm

Gripper
```

Dashboard 显示：

```text
Mini V3

RML63

Gripper
```

三个 Mock 设备。

点击底盘：

```text
前进
```

后端 Mock 状态变化：

```text
linear_velocity > 0
```

WebSocket 将变化返回前端。

点击：

```text
Stop
```

速度变为：

```text
0
```

机械臂和夹爪同样能够通过 Mock Controller 完成基本状态变化。

如果以上流程正常：

说明：

```text
Frontend
   ↓
REST API
   ↓
RobotManager
   ↓
Controller
   ↓
StateManager
   ↓
WebSocket
   ↓
Frontend
```

这一整套基础架构已经成立。

之后才进入真实 ROS2 和机器人设备接入阶段。

---

## 19. 后续开发顺序

严格按照以下顺序推进：

```text
01 系统骨架
       ↓
02 Mock 设备
       ↓
03 Web 前后端通信
       ↓
04 ROS2 Adapter
       ↓
05 Mini V3
       ↓
06 RML63
       ↓
07 Gripper
       ↓
08 状态监控
       ↓
09 系统联调
       ↓
10 3D 可视化
       ↓
11 Camera
       ↓
12 Navigation
       ↓
13 Vision
       ↓
14 Autonomous Grasp
```

---

## 20. 当前最重要的原则

当前阶段不要追求：

> “尽快让网页控制机器人。”

而应该优先保证：

> “未来增加任何机器人模块时，不需要推翻现在的代码。”

因此第一步开发的核心不是设备控制，而是：

```text
统一架构

设备抽象

数据流

状态管理

Web 通信

ROS2 隔离层
```

这五部分稳定以后，再逐个接入实际硬件。

---

## 21. 当前版本结论

V0.1 阶段只确定整个项目的大框架。

暂不讨论：

```text
Mini V3 具体 Topic

RML63 具体 SDK

夹爪通信协议

ROS2 消息字段

机械臂运动指令
```

这些内容将在后续开发阶段逐项调查、验证、记录并接入。

下一阶段：

> **Phase 0：建立项目骨架 + Mock Robot 系统**

完成 Phase 0 后，再进入 ROS2 基础通信层开发。
