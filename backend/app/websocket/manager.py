from fastapi import WebSocket, WebSocketDisconnect

from app.core.state_manager import StateManager
from app.core.map_manager import MapManager


async def websocket_endpoint(websocket: WebSocket, state_manager: StateManager) -> None:
    """Push an initial snapshot and each subsequent StateManager revision."""
    await websocket.accept()
    version, state = await state_manager.snapshot()
    try:
        await websocket.send_json(
            {"type": "robot_state", "version": version, "data": state.model_dump(mode="json")}
        )
        while True:
            next_version, next_state = await state_manager.wait_for_update(version)
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


async def map_websocket_endpoint(websocket: WebSocket, manager: MapManager) -> None:
    await websocket.accept()
    version, snapshot = await manager.snapshot()
    try:
        await websocket.send_json({"type": "map", "version": version, "data": snapshot.model_dump(mode="json")})
        while True:
            next_version, snapshot = await manager.wait_for_update(version)
            if next_version == version:
                await websocket.send_json({"type": "heartbeat", "version": version})
            else:
                version = next_version
                await websocket.send_json({"type": "map", "version": version, "data": snapshot.model_dump(mode="json")})
    except (WebSocketDisconnect, RuntimeError):
        return
