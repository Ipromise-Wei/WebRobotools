import asyncio
from copy import deepcopy

from app.models.system import RobotState


class StateManager:
    """Single source of truth for all robot state exposed to clients."""

    def __init__(self) -> None:
        self._state = RobotState()
        self._version = 0
        self._condition = asyncio.Condition()

    async def snapshot(self) -> tuple[int, RobotState]:
        async with self._condition:
            return self._version, deepcopy(self._state)

    async def replace(self, state: RobotState) -> int:
        async with self._condition:
            self._state = deepcopy(state)
            self._version += 1
            self._condition.notify_all()
            return self._version

    async def wait_for_update(
        self, known_version: int, timeout: float = 15.0
    ) -> tuple[int, RobotState]:
        async with self._condition:
            if self._version == known_version:
                try:
                    await asyncio.wait_for(
                        self._condition.wait_for(lambda: self._version != known_version),
                        timeout=timeout,
                    )
                except asyncio.TimeoutError:
                    pass
            return self._version, deepcopy(self._state)
