import asyncio
from typing import Any

import httpx
from fastapi import WebSocketDisconnect

from app.main import app
from app.websocket.manager import websocket_endpoint


async def _run_api_scenario() -> None:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            initial = await client.get("/api/system/status")
            assert initial.status_code == 200
            assert initial.json()["system"] == {
                "backend": True,
                "ros2": False,
                "mode": "mock",
            }
            assert initial.json()["chassis"]["connected"] is True

            moved = await client.post(
                "/api/chassis/move", json={"linear": 0.3, "angular": 0.0}
            )
            assert moved.status_code == 200
            assert moved.json()["state"]["chassis"]["linear_velocity"] == 0.3

            stopped = await client.post("/api/chassis/stop")
            assert stopped.json()["state"]["chassis"]["moving"] is False

            arm = await client.post(
                "/api/arm/joints", json={"positions": [1, 2, 3, 4, 5, 6]}
            )
            assert arm.status_code == 200
            assert arm.json()["state"]["arm"]["joints"] == [1, 2, 3, 4, 5, 6]

            gripper = await client.post("/api/gripper/close")
            assert gripper.status_code == 200
            assert gripper.json()["state"]["gripper"]["status"] == "closed"

            invalid_speed = await client.post(
                "/api/chassis/move", json={"linear": 4, "angular": 0}
            )
            invalid_joints = await client.post(
                "/api/arm/joints", json={"positions": [1, 2]}
            )
            assert invalid_speed.status_code == 422
            assert invalid_joints.status_code == 422


def test_api_state_and_device_commands() -> None:
    asyncio.run(_run_api_scenario())


class RecordingWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.initial_sent = asyncio.Event()

    async def accept(self) -> None:
        return None

    async def send_json(self, message: dict[str, Any]) -> None:
        self.messages.append(message)
        if len(self.messages) == 1:
            self.initial_sent.set()
        if len(self.messages) == 2:
            raise WebSocketDisconnect()


async def _run_websocket_scenario() -> None:
    async with app.router.lifespan_context(app):
        socket = RecordingWebSocket()
        task = asyncio.create_task(
            websocket_endpoint(socket, app.state.state_manager)  # type: ignore[arg-type]
        )
        await asyncio.wait_for(socket.initial_sent.wait(), timeout=1)
        await app.state.robot_manager.close_gripper()
        await asyncio.wait_for(task, timeout=1)

        assert socket.messages[0]["type"] == "robot_state"
        assert socket.messages[1]["type"] == "robot_state"
        assert socket.messages[1]["data"]["gripper"]["status"] == "closed"
        assert socket.messages[1]["version"] > socket.messages[0]["version"]


def test_websocket_pushes_state_revisions() -> None:
    asyncio.run(_run_websocket_scenario())
