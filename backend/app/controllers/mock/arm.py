from copy import deepcopy

from app.controllers.base.arm_base import ArmController
from app.models.arm import ArmState, Pose


class MockArm(ArmController):
    def __init__(self, connected: bool = True) -> None:
        self._state = ArmState(connected=connected)

    async def connect(self) -> None:
        self._state.connected = True
        self._state.error = ""

    async def disconnect(self) -> None:
        self._state.connected = False
        self._state.moving = False

    async def move_joint(self, joint: int, position: float, speed: int | None = None) -> None:
        self._state.joints[joint - 1] = position
        self._state.moving = True

    async def move_joints(self, positions: list[float], speed: int | None = None) -> None:
        self._state.joints = list(positions)
        self._state.moving = True

    async def move_pose(self, pose: Pose, speed: int | None = None) -> None:
        self._state.pose = pose.model_copy(deep=True)
        self._state.moving = True

    async def stop(self) -> None:
        self._state.moving = False

    async def get_joint_state(self) -> list[float]:
        return list(self._state.joints)

    async def get_pose(self) -> Pose:
        return self._state.pose.model_copy(deep=True)

    async def get_state(self) -> ArmState:
        return deepcopy(self._state)

    async def is_connected(self) -> bool:
        return self._state.connected
