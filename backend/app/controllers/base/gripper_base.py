from abc import ABC, abstractmethod

from app.models.gripper import GripperState


class GripperController(ABC):
    @abstractmethod
    async def open(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def set_position(self, position: float) -> None: ...

    @abstractmethod
    async def set_force(self, force: float) -> None: ...

    @abstractmethod
    async def get_state(self) -> GripperState: ...

    @abstractmethod
    async def is_connected(self) -> bool: ...

