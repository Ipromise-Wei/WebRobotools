import asyncio
from collections.abc import Callable

from app.controllers.base.arm_base import ArmController
from app.controllers.base.chassis_base import ChassisController
from app.controllers.base.gripper_base import GripperController
from app.controllers.mock.arm import MockArm
from app.controllers.mock.chassis import MockChassis
from app.controllers.mock.gripper import MockGripper
from app.core.state_manager import StateManager
from app.models.arm import Pose
from app.models.system import RobotState, SystemState


class RobotManager:
    """Coordinates device controllers and publishes their state atomically."""

    def __init__(
        self,
        chassis: ChassisController,
        arm: ArmController,
        gripper: GripperController,
        state_manager: StateManager,
        mode: str = "mock",
        ros2_status: Callable[[], bool] | None = None,
        poll_interval: float = 0.2,
    ) -> None:
        self.chassis = chassis
        self.arm = arm
        self.gripper = gripper
        self.state_manager = state_manager
        self.mode = mode
        self._ros2_status = ros2_status or (lambda: False)
        self._poll_interval = poll_interval
        self._command_lock = asyncio.Lock()
        self._running = False
        self._poll_task: asyncio.Task[None] | None = None

    @classmethod
    def create_mock(cls, state_manager: StateManager) -> "RobotManager":
        return cls(MockChassis(), MockArm(), MockGripper(), state_manager)

    async def initialize(self) -> None:
        self._running = True
        await self._sync_state()
        if self.mode == "ros2":
            self._poll_task = asyncio.create_task(self._poll())

    async def shutdown(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        async with self._command_lock:
            await asyncio.gather(
                self.chassis.stop(), self.arm.stop(), self.gripper.stop(),
                return_exceptions=True,
            )
            self._running = False
            await self._sync_state()

    async def _sync_state(self) -> RobotState:
        state = RobotState(
            system=SystemState(backend=self._running, ros2=self._ros2_status(), mode=self.mode),
            chassis=await self.chassis.get_state(),
            arm=await self.arm.get_state(),
            gripper=await self.gripper.get_state(),
        )
        await self.state_manager.replace(state)
        return state

    async def _poll(self) -> None:
        while self._running:
            await asyncio.sleep(self._poll_interval)
            async with self._command_lock:
                await self._sync_state()

    async def get_state(self) -> RobotState:
        _, state = await self.state_manager.snapshot()
        return state

    async def connect_arm(self) -> RobotState:
        async with self._command_lock:
            try:
                await self.arm.connect()
            except Exception:
                await self._sync_state()
                raise
            return await self._sync_state()

    async def disconnect_arm(self) -> RobotState:
        async with self._command_lock:
            # Refresh trajectory state before releasing tool IO or closing the
            # tunnel. The controller refuses disconnect while motion is active.
            await self.arm.get_state()
            await self.gripper.stop()
            await self.arm.disconnect()
            return await self._sync_state()

    async def move_chassis(self, linear: float, angular: float) -> RobotState:
        async with self._command_lock:
            await self.chassis.move(linear, angular)
            return await self._sync_state()

    async def stop_chassis(self) -> RobotState:
        async with self._command_lock:
            await self.chassis.stop()
            return await self._sync_state()

    async def move_arm_joint(self, joint: int, position: float, speed: int | None = None) -> RobotState:
        async with self._command_lock:
            await self.arm.move_joint(joint, position, speed)
            return await self._sync_state()

    async def move_arm_joints(self, positions: list[float], speed: int | None = None) -> RobotState:
        async with self._command_lock:
            await self.arm.move_joints(positions, speed)
            return await self._sync_state()

    async def move_arm_pose(self, pose: Pose, speed: int | None = None) -> RobotState:
        async with self._command_lock:
            await self.arm.move_pose(pose, speed)
            return await self._sync_state()

    async def stop_arm(self) -> RobotState:
        async with self._command_lock:
            await self.arm.stop()
            return await self._sync_state()

    async def stop_manipulator(self) -> RobotState:
        # Do not queue the stop request behind a higher-level command lock. The
        # shared hardware client still serializes wire access, but can send the
        # stop as soon as the in-flight controller packet is acknowledged.
        results = await asyncio.gather(
            self.arm.stop(), self.gripper.stop(), return_exceptions=True
        )
        async with self._command_lock:
            errors = [str(result) for result in results if isinstance(result, Exception)]
            state = await self._sync_state()
            if errors:
                raise RuntimeError("；".join(errors))
            return state

    async def open_gripper(self) -> RobotState:
        async with self._command_lock:
            await self.gripper.open()
            return await self._sync_state()

    async def close_gripper(self) -> RobotState:
        async with self._command_lock:
            await self.gripper.close()
            return await self._sync_state()

    async def stop_gripper(self) -> RobotState:
        async with self._command_lock:
            await self.gripper.stop()
            return await self._sync_state()
