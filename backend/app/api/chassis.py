from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.dependencies import get_robot_manager
from app.core.robot_manager import RobotManager
from app.models.chassis import ChassisMoveRequest, ChassisState
from app.models.system import CommandResponse

router = APIRouter()


@router.get("/status", response_model=ChassisState)
async def get_chassis_status(
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> ChassisState:
    return (await manager.get_state()).chassis


@router.post("/move", response_model=CommandResponse)
async def move_chassis(
    command: ChassisMoveRequest,
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> CommandResponse:
    return CommandResponse(state=await manager.move_chassis(command.linear, command.angular))


@router.post("/stop", response_model=CommandResponse)
async def stop_chassis(
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> CommandResponse:
    return CommandResponse(state=await manager.stop_chassis())

