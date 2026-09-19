from copy import deepcopy

from app.controllers.base.gripper_base import GripperController
from app.models.gripper import GripperState


class MockGripper(GripperController):
    def __init__(self, connected: bool = True) -> None:
        self._state = GripperState(connected=connected, status="opened", position=1.0)
        self._force = 0.5

    async def open(self) -> None:
        self._state.status = "opened"
        self._state.position = 1.0
        self._state.moving = False

    async def close(self) -> None:
        self._state.status = "closed"
        self._state.position = 0.0
        self._state.moving = False

    async def stop(self) -> None:
        self._state.status = "stopped"
        self._state.moving = False

    async def set_position(self, position: float) -> None:
        self._state.position = max(0.0, min(1.0, position))
        self._state.status = "opened" if position > 0.5 else "closed"

    async def set_force(self, force: float) -> None:
        self._force = max(0.0, min(1.0, force))

    async def get_state(self) -> GripperState:
        return deepcopy(self._state)

    async def is_connected(self) -> bool:
        return self._state.connected
