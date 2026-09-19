# Robot Web Control

面向移动操作机器人的 Web 一体化控制基础框架。当前实现对应开发计划的 Phase 0/1：使用 Mock 设备打通浏览器、REST API、统一控制层、状态管理和 WebSocket 实时推送，不连接真实机器人。

## 当前功能

- FastAPI 后端与 Vue 3 + TypeScript 前端
- `ChassisController`、`ArmController`、`GripperController` 抽象接口
- Mock Mini V3、Mock RML63 与 Mock Gripper
- 底盘、机械臂、夹爪 REST API
- 统一 `RobotManager` 与 `StateManager`
- `/ws/robot` 实时状态推送
- Dashboard、底盘、机械臂、夹爪和系统状态页面

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

## 测试与构建

```bash
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest
cd frontend && npm run build
```

系统边界及接口约定见 [docs/architecture.md](docs/architecture.md) 和 [docs/api.md](docs/api.md)。
