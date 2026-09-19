import asyncio
from copy import deepcopy

from app.models.visualization import MapSnapshot


class MapManager:
    def __init__(self) -> None:
        self._snapshot = MapSnapshot()
        self._version = 0
        self._condition = asyncio.Condition()

    async def snapshot(self) -> tuple[int, MapSnapshot]:
        async with self._condition:
            return self._version, deepcopy(self._snapshot)

    async def replace(self, snapshot: MapSnapshot) -> None:
        async with self._condition:
            self._snapshot = deepcopy(snapshot)
            self._version += 1
            self._condition.notify_all()

    async def wait_for_update(self, version: int) -> tuple[int, MapSnapshot]:
        async with self._condition:
            if self._version == version:
                try:
                    await asyncio.wait_for(
                        self._condition.wait_for(lambda: self._version != version), 15
                    )
                except TimeoutError:
                    pass
            return self._version, deepcopy(self._snapshot)
