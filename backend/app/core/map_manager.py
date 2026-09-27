import asyncio
from typing import Any

from app.core.map_transport import compose_map_payload, encode_map_grid
from app.models.visualization import MapSnapshot


class MapManager:
    """Publishes immutable map snapshots without copying full occupancy grids."""

    def __init__(self) -> None:
        self._snapshot = MapSnapshot()
        self._grid_payload: dict[str, Any] | None = None
        self._grid_revision = -1
        self._version = 0
        self._condition = asyncio.Condition()
        self._payload_lock = asyncio.Lock()

    async def snapshot(self) -> tuple[int, MapSnapshot]:
        async with self._condition:
            return self._version, self._snapshot

    async def replace(self, snapshot: MapSnapshot) -> None:
        async with self._condition:
            # ROS2NodeAdapter always replaces (rather than mutates) published
            # snapshots. Sharing one grid list prevents multi-megabyte copies
            # for every poll and every connected map client.
            self._snapshot = snapshot
            # No browser may be viewing the map. Defer compression until a
            # REST or WebSocket consumer actually asks for this revision.
            if snapshot.revision != self._grid_revision:
                self._grid_payload = None
            self._version += 1
            self._condition.notify_all()

    async def wait_for_update(self, version: int) -> tuple[int, MapSnapshot]:
        async with self._condition:
            if self._version == version:
                try:
                    await asyncio.wait_for(
                        self._condition.wait_for(lambda: self._version != version), 15
                    )
                except asyncio.TimeoutError:
                    pass
            return self._version, self._snapshot

    async def transport_snapshot(self) -> tuple[int, dict[str, Any]]:
        # Coalesce simultaneous REST and WebSocket reads into one background
        # encoding operation. Compression never runs on FastAPI's event loop.
        async with self._payload_lock:
            while True:
                async with self._condition:
                    version = self._version
                    snapshot = self._snapshot
                    if (
                        self._grid_payload is not None
                        and self._grid_revision == snapshot.revision
                    ):
                        return version, compose_map_payload(self._grid_payload, snapshot)
                payload = await asyncio.to_thread(encode_map_grid, snapshot)
                async with self._condition:
                    # Path updates may arrive while the grid is being encoded.
                    # They do not invalidate its bytes, so reuse the result
                    # and attach the newer path instead of compressing again.
                    if self._snapshot.revision == snapshot.revision:
                        self._grid_payload = payload
                        self._grid_revision = snapshot.revision
                        return self._version, compose_map_payload(payload, self._snapshot)

    async def wait_for_transport_update(
        self, version: int
    ) -> tuple[int, dict[str, Any]]:
        async with self._condition:
            if self._version == version:
                try:
                    await asyncio.wait_for(
                        self._condition.wait_for(lambda: self._version != version), 15
                    )
                except asyncio.TimeoutError:
                    pass
        return await self.transport_snapshot()
