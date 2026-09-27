import asyncio
from typing import Protocol

from app.core.map_manager import MapManager
from app.models.visualization import MapSnapshot


class MapProvider(Protocol):
    def get_map(self) -> MapSnapshot: ...


class VisualizationService:
    def __init__(self, manager: MapManager, provider: MapProvider | None, interval: float) -> None:
        self.manager, self.provider, self.interval = manager, provider, interval
        self.task: asyncio.Task[None] | None = None
        self.revision = -1
        self.path_revision = -1

    async def start(self) -> None:
        if self.provider:
            self.task = asyncio.create_task(self._poll())

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def _poll(self) -> None:
        while True:
            snapshot = self.provider.get_map()
            if (
                snapshot.revision != self.revision
                or snapshot.path_revision != self.path_revision
            ):
                self.revision = snapshot.revision
                self.path_revision = snapshot.path_revision
                await self.manager.replace(snapshot)
            await asyncio.sleep(self.interval)
