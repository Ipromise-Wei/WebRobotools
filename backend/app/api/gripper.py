from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import get_settings
from app.core.dependencies import get_robot_manager
from app.core.robot_manager import RobotManager
from app.models.gripper import GripperState
from app.models.system import CommandResponse

router = APIRouter()


def require_true_hardware() -> None:
    settings = get_settings()
    if settings.robot.mode != "ros2" or not settings.arm.enabled or not settings.gripper.enabled:
        raise HTTPException(status_code=423, detail="夹爪接口仅允许 RML63 真机模式")


@router.get("/status", response_model=GripperState)
async def get_gripper_status(
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> GripperState:
    return (await manager.get_state()).gripper


@router.post("/open", response_model=CommandResponse)
async def open_gripper(
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> CommandResponse:
    require_true_hardware()
    return CommandResponse(state=await manager.open_gripper())


@router.post("/close", response_model=CommandResponse)
async def close_gripper(
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> CommandResponse:
    require_true_hardware()
    return CommandResponse(state=await manager.close_gripper())


@router.post("/stop", response_model=CommandResponse)
async def stop_gripper(
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> CommandResponse:
    require_true_hardware()
    return CommandResponse(state=await manager.stop_gripper())
