from fastapi import Request

from app.core.robot_manager import RobotManager
from app.core.state_manager import StateManager


async def get_robot_manager(request: Request) -> RobotManager:
    return request.app.state.robot_manager


async def get_state_manager(request: Request) -> StateManager:
    return request.app.state.state_manager
