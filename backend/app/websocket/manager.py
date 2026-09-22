from collections.abc import Callable

from fastapi import WebSocket, WebSocketDisconnect

from app.core.state_manager import StateManager
from app.core.map_manager import MapManager


async def websocket_endpoint(
    websocket: WebSocket,
    state_manager: StateManager,
    is_authorized: Callable[[], bool] | None = None,
) -> None:
    """Push an initial snapshot and each subsequent StateManager revision."""
    await websocket.accept()
    version, state = await state_manager.snapshot()
    try:
        await websocket.send_json(
            {"type": "robot_state", "version": version, "data": state.model_dump(mode="json")}
        )
        while True:
            next_version, next_state = await state_manager.wait_for_update(version)
            if is_authorized is not None and not is_authorized():
                await websocket.close(code=4401, reason="Session expired")
                return
            if next_version == version:
                await websocket.send_json({"type": "heartbeat", "version": version})
                continue
            version = next_version
            await websocket.send_json(
                {
                    "type": "robot_state",
                    "version": version,
                    "data": next_state.model_dump(mode="json"),
                }
            )
    except (WebSocketDisconnect, RuntimeError):
        return


async def map_websocket_endpoint(
    websocket: WebSocket,
    manager: MapManager,
    is_authorized: Callable[[], bool] | None = None,
) -> None:
    await websocket.accept()
    version, snapshot = await manager.snapshot()
    try:
        await websocket.send_json({"type": "map", "version": version, "data": snapshot.model_dump(mode="json")})
        while True:
            next_version, snapshot = await manager.wait_for_update(version)
            if is_authorized is not None and not is_authorized():
                await websocket.close(code=4401, reason="Session expired")
                return
            if next_version == version:
                await websocket.send_json({"type": "heartbeat", "version": version})
            else:
                version = next_version
                await websocket.send_json({"type": "map", "version": version, "data": snapshot.model_dump(mode="json")})
    except (WebSocketDisconnect, RuntimeError):
        return
