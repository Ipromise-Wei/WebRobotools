from abc import ABC, abstractmethod

from app.models.arm import ArmState, Pose


class ArmController(ABC):
    @abstractmethod
    async def move_joint(self, joint: int, position: float) -> None: ...

    @abstractmethod
    async def move_joints(self, positions: list[float]) -> None: ...

    @abstractmethod
    async def move_pose(self, pose: Pose) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def get_joint_state(self) -> list[float]: ...

    @abstractmethod
    async def get_pose(self) -> Pose: ...

    @abstractmethod
    async def get_state(self) -> ArmState: ...

    @abstractmethod
    async def is_connected(self) -> bool: ...

