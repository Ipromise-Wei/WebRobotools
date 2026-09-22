from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_remote_runtime, get_robot_manager
from app.core.robot_manager import RobotManager
from app.core.config import get_settings
from app.core.remote_runtime import RemoteRuntimeError, RemoteRuntimeManager
from app.models.arm import ArmConfigResponse, ArmJointRequest, ArmJointsRequest, ArmPoseRequest, ArmState, Pose
from app.models.system import CommandResponse

router = APIRouter()


def require_true_hardware() -> None:
    settings = get_settings()
    if settings.robot.mode != "ros2" or not settings.arm.enabled:
        raise HTTPException(status_code=423, detail="机械臂接口仅允许 ROS2 真机模式")


@router.get("/config", response_model=ArmConfigResponse)
async def get_arm_config() -> ArmConfigResponse:
    app_settings = get_settings()
    settings = app_settings.arm
    return ArmConfigResponse(
        enabled=settings.enabled,
        motion_commands_enabled=(
            app_settings.robot.mode == "ros2"
            and settings.enabled
            and settings.allow_motion_commands
        ),
        transport=settings.transport,
        host=settings.host,
        port=settings.port,
        network_interface=settings.network_interface,
        expected_tool=settings.expected_tool,
        collision_level=settings.collision_level,
        joint_speed_percent=settings.joint_speed_percent,
        pose_speed_percent=settings.pose_speed_percent,
        workspace_min_m=settings.workspace_min_m,
        workspace_max_m=settings.workspace_max_m,
        max_pose_segment_m=settings.max_pose_segment_m,
        keepout_enabled=settings.keepout_enabled,
        standby_joints_deg=settings.standby_joints_deg,
        gripper_enabled=app_settings.gripper.enabled,
        gripper_commands_enabled=(
            app_settings.robot.mode == "ros2"
            and app_settings.arm.enabled
            and app_settings.gripper.enabled
            and app_settings.gripper.allow_commands
        ),
    )


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


@router.post("/connect", response_model=CommandResponse)
async def connect_arm(
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
    remote_runtime: Annotated[RemoteRuntimeManager, Depends(get_remote_runtime)],
) -> CommandResponse:
    require_true_hardware()
    try:
        await remote_runtime.ensure_arm_bridge_deployed()
    except (OSError, RemoteRuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"无法在工控机部署机械臂桥接器：{exc}",
        ) from exc
    return CommandResponse(state=await manager.connect_arm())


@router.post("/disconnect", response_model=CommandResponse)
async def disconnect_arm(
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> CommandResponse:
    require_true_hardware()
    return CommandResponse(state=await manager.disconnect_arm())


@router.post("/joint", response_model=CommandResponse)
async def move_arm_joint(
    command: ArmJointRequest,
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> CommandResponse:
    require_true_hardware()
    return CommandResponse(
        state=await manager.move_arm_joint(command.joint, command.position, command.speed)
    )


@router.post("/joints", response_model=CommandResponse)
async def move_arm_joints(
    command: ArmJointsRequest,
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> CommandResponse:
    require_true_hardware()
    return CommandResponse(state=await manager.move_arm_joints(command.positions, command.speed))


@router.post("/pose", response_model=CommandResponse)
async def move_arm_pose(
    command: ArmPoseRequest,
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> CommandResponse:
    require_true_hardware()
    pose = Pose(**command.model_dump(exclude={"speed"}))
    return CommandResponse(state=await manager.move_arm_pose(pose, command.speed))


@router.post("/stop", response_model=CommandResponse)
async def stop_arm(
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> CommandResponse:
    require_true_hardware()
    return CommandResponse(state=await manager.stop_arm())


@router.post("/emergency-stop", response_model=CommandResponse)
async def emergency_stop_manipulator(
    manager: Annotated[RobotManager, Depends(get_robot_manager)],
) -> CommandResponse:
    require_true_hardware()
    try:
        return CommandResponse(state=await manager.stop_manipulator())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
