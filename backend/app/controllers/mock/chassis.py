from copy import deepcopy

from app.controllers.base.chassis_base import ChassisController
from app.models.chassis import ChassisState


class MockChassis(ChassisController):
    def __init__(self) -> None:
        self._state = ChassisState(connected=True)

    async def move(self, linear: float, angular: float) -> None:
        self._state.linear_velocity = linear
        self._state.angular_velocity = angular
        self._state.moving = linear != 0.0 or angular != 0.0

    async def stop(self) -> None:
        await self.move(0.0, 0.0)

    async def get_state(self) -> ChassisState:
        return deepcopy(self._state)

    async def is_connected(self) -> bool:
        return self._state.connected

