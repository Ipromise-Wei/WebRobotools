import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.ros2.node import MotionControlDisabled, ROS2NodeAdapter
from app.api import arm, chassis, gripper, runtime, system, visualization
from app.controllers.arm.realman import (
    ArmMotionDisabled,
    RealManArmController,
    RealManClient,
    RealManControllerError,
    RealManGripperController,
)
from app.controllers.chassis.mini_v3 import MiniV3ChassisController
from app.controllers.mock.arm import MockArm
from app.controllers.mock.gripper import MockGripper
from app.core.config import get_settings
from app.core.logger import configure_logging
from app.core.map_manager import MapManager
from app.core.realsense_stream import RealSenseStream
from app.core.robot_manager import RobotManager
from app.core.remote_runtime import RemoteRuntimeError, RemoteRuntimeManager
from app.core.state_manager import StateManager
from app.core.visualization_service import VisualizationService
from app.websocket.manager import map_websocket_endpoint, websocket_endpoint


async def deploy_arm_bridge(remote_runtime: RemoteRuntimeManager) -> None:
    try:
        await remote_runtime.ensure_deployed()
    except (OSError, RemoteRuntimeError) as exc:
        logging.getLogger(__name__).warning(
            "Unable to deploy industrial-PC arm bridge: %s", exc
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.server.log_level)
    state_manager = StateManager()
    map_manager = MapManager()
    realsense_stream = RealSenseStream(
        settings.visualization.realsense,
        settings.remote_runtime,
    )
    remote_runtime = RemoteRuntimeManager(settings.remote_runtime)
    adapter: ROS2NodeAdapter | None = None
    realman_client: RealManClient | None = None
    arm_bridge_deploy_task = None
    if settings.robot.mode == "ros2":
        adapter = ROS2NodeAdapter(settings.ros2)
        adapter.start()
        if settings.arm.enabled:
            if settings.arm.transport == "industrial_pc":
                arm_bridge_deploy_task = asyncio.create_task(
                    deploy_arm_bridge(remote_runtime)
                )
            realman_client = RealManClient(
                settings.arm, settings.gripper, settings.remote_runtime
            )
            arm_controller = RealManArmController(realman_client, settings.arm)
            gripper_controller = RealManGripperController(realman_client)
        else:
            arm_controller = MockArm(connected=False)
            gripper_controller = MockGripper(connected=False)
        robot_manager = RobotManager(
            MiniV3ChassisController(adapter), arm_controller,
            gripper_controller, state_manager,
            mode="ros2", ros2_status=adapter.is_running,
            poll_interval=settings.robot.state_poll_interval,
        )
    else:
        robot_manager = RobotManager.create_mock(state_manager)
    visualization_service = VisualizationService(map_manager, adapter, settings.robot.state_poll_interval)
    app.state.settings = settings
    app.state.state_manager = state_manager
    app.state.map_manager = map_manager
    app.state.realsense_stream = realsense_stream
    app.state.robot_manager = robot_manager
    app.state.remote_runtime = remote_runtime
    app.state.ros2_adapter = adapter
    await robot_manager.initialize()
    await visualization_service.start()
    await realsense_stream.start()
    try:
        yield
    finally:
        if arm_bridge_deploy_task:
            await arm_bridge_deploy_task
        await realsense_stream.stop()
        await visualization_service.stop()
        await robot_manager.shutdown()
        if realman_client:
            await realman_client.close()
        if adapter:
            adapter.stop()


settings = get_settings()
app = FastAPI(
    title=settings.server.app_name,
    version="0.4.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.server.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(chassis.router, prefix="/api/chassis", tags=["chassis"])
app.include_router(arm.router, prefix="/api/arm", tags=["arm"])
app.include_router(gripper.router, prefix="/api/gripper", tags=["gripper"])
app.include_router(visualization.router, prefix="/api/visualization", tags=["visualization"])
app.include_router(runtime.router, prefix="/api/runtime", tags=["runtime"])


@app.exception_handler(MotionControlDisabled)
async def motion_locked(_: Request, exc: MotionControlDisabled) -> JSONResponse:
    return JSONResponse(status_code=423, content={"detail": str(exc)})


@app.exception_handler(ArmMotionDisabled)
async def arm_motion_locked(_: Request, exc: ArmMotionDisabled) -> JSONResponse:
    return JSONResponse(status_code=423, content={"detail": str(exc)})


@app.exception_handler(RealManControllerError)
async def arm_controller_error(_: Request, exc: RealManControllerError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws/robot")
async def robot_websocket(websocket: WebSocket) -> None:
    await websocket_endpoint(websocket, websocket.app.state.state_manager)


@app.websocket("/ws/map")
async def map_websocket(websocket: WebSocket) -> None:
    await map_websocket_endpoint(websocket, websocket.app.state.map_manager)
