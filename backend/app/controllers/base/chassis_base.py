from abc import ABC, abstractmethod

from app.models.chassis import ChassisState


class ChassisController(ABC):
    @abstractmethod
    async def move(self, linear: float, angular: float) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def get_state(self) -> ChassisState: ...

    @abstractmethod
    async def is_connected(self) -> bool: ...

