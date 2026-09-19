from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.dependencies import get_robot_manager
from app.core.robot_manager import RobotManager
from app.models.gripper import GripperState
from app.models.system import CommandResponse

router = APIRouter()


@router.get("/status", response_model=GripperState)
async def get_gripper_status(
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> GripperState:
    return (await manager.get_state()).gripper


@router.post("/open", response_model=CommandResponse)
async def open_gripper(
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> CommandResponse:
    return CommandResponse(state=await manager.open_gripper())


@router.post("/close", response_model=CommandResponse)
async def close_gripper(
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> CommandResponse:
    return CommandResponse(state=await manager.close_gripper())


@router.post("/stop", response_model=CommandResponse)
async def stop_gripper(
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> CommandResponse:
    return CommandResponse(state=await manager.stop_gripper())

