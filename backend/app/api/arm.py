from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.dependencies import get_robot_manager
from app.core.robot_manager import RobotManager
from app.models.arm import ArmJointRequest, ArmJointsRequest, ArmPoseRequest, ArmState, Pose
from app.models.system import CommandResponse

router = APIRouter()


@router.get("/status", response_model=ArmState)
async def get_arm_status(
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> ArmState:
    return (await manager.get_state()).arm


@router.get("/joints", response_model=list[float])
async def get_arm_joints(
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> list[float]:
    return (await manager.get_state()).arm.joints


@router.get("/pose", response_model=Pose)
async def get_arm_pose(
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> Pose:
    return (await manager.get_state()).arm.pose


@router.post("/joint", response_model=CommandResponse)
async def move_arm_joint(
    command: ArmJointRequest,
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> CommandResponse:
    return CommandResponse(
        state=await manager.move_arm_joint(command.joint, command.position)
    )


@router.post("/joints", response_model=CommandResponse)
async def move_arm_joints(
    command: ArmJointsRequest,
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> CommandResponse:
    return CommandResponse(state=await manager.move_arm_joints(command.positions))


@router.post("/pose", response_model=CommandResponse)
async def move_arm_pose(
    command: ArmPoseRequest,
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> CommandResponse:
    return CommandResponse(state=await manager.move_arm_pose(Pose(**command.model_dump())))


@router.post("/stop", response_model=CommandResponse)
async def stop_arm(
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> CommandResponse:
    return CommandResponse(state=await manager.stop_arm())

