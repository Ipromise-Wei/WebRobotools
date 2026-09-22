from app.adapters.ros2.node import ROS2NodeAdapter
from app.controllers.base.chassis_base import ChassisController
from app.models.chassis import ChassisState


class MiniV3ChassisController(ChassisController):
    def __init__(self, adapter: ROS2NodeAdapter) -> None:
        self.adapter = adapter

    async def move(self, linear: float, angular: float) -> None:
        self.adapter.set_velocity(linear, angular)

    async def stop(self) -> None:
        if self.adapter.config.allow_motion_commands:
            await self.adapter.cancel_navigation()
            self.adapter.set_velocity(0.0, 0.0)

    async def get_state(self) -> ChassisState:
        return self.adapter.get_chassis_state()

    async def is_connected(self) -> bool:
        return self.adapter.get_chassis_state().connected
