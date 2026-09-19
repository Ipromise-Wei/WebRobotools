from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from app.api import arm, chassis, gripper, system
from app.core.config import get_settings
from app.core.logger import configure_logging
from app.core.robot_manager import RobotManager
from app.core.state_manager import StateManager
from app.websocket.manager import websocket_endpoint


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    state_manager = StateManager()
    robot_manager = RobotManager.create_mock(state_manager)
    app.state.state_manager = state_manager
    app.state.robot_manager = robot_manager
    await robot_manager.initialize()
    try:
        yield
    finally:
        await robot_manager.shutdown()


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(chassis.router, prefix="/api/chassis", tags=["chassis"])
app.include_router(arm.router, prefix="/api/arm", tags=["arm"])
app.include_router(gripper.router, prefix="/api/gripper", tags=["gripper"])


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws/robot")
async def robot_websocket(websocket: WebSocket) -> None:
    await websocket_endpoint(websocket, websocket.app.state.state_manager)

