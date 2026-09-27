import asyncio

from app.models.visualization import MapSnapshot


class MapManager:
    """Publishes immutable map snapshots without copying full occupancy grids."""

    def __init__(self) -> None:
        self._snapshot = MapSnapshot()
        self._version = 0
        self._condition = asyncio.Condition()

    async def snapshot(self) -> tuple[int, MapSnapshot]:
        async with self._condition:
            return self._version, self._snapshot

    async def replace(self, snapshot: MapSnapshot) -> None:
        async with self._condition:
            # ROS2NodeAdapter always replaces (rather than mutates) published
            # snapshots. Sharing one grid list prevents multi-megabyte copies
            # for every poll and every connected map client.
            self._snapshot = snapshot
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
            return self._version, self._snapshot
