from fastapi import Request

from app.core.robot_manager import RobotManager
from app.core.state_manager import StateManager
from app.core.map_manager import MapManager
from app.core.remote_runtime import RemoteRuntimeManager


async def get_robot_manager(request: Request) -> RobotManager:
    return request.app.state.robot_manager


async def get_state_manager(request: Request) -> StateManager:
    return request.app.state.state_manager


async def get_map_manager(request: Request) -> MapManager:
    return request.app.state.map_manager


async def get_remote_runtime(request: Request) -> RemoteRuntimeManager:
    return request.app.state.remote_runtime
