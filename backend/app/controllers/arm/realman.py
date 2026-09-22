"""RealMan RML63 JSON/TCP controllers adapted from grasp_studio.

The arm and tool-IO controllers share one serialized TCP client. Browser
requests can only select the typed operations exposed by the API; raw JSON/TCP
payloads are never accepted from the Web client.
"""

from __future__ import annotations

import asyncio
import codecs
from copy import deepcopy
import json
import math
import os
from pathlib import PurePosixPath
import select
import shlex
import socket
import subprocess
import threading
import time
from typing import Any, Callable, Protocol

from app.controllers.base.arm_base import ArmController
from app.controllers.base.gripper_base import GripperController
from app.core.config import ArmSettings, GripperSettings, RemoteRuntimeSettings
from app.models.arm import ArmState, Pose
from app.models.gripper import GripperState


class ArmMotionDisabled(RuntimeError):
    pass


class RealManControllerError(RuntimeError):
    pass


class ArmTransport(Protocol):
    def settimeout(self, timeout: float) -> None: ...
    def sendall(self, data: bytes) -> None: ...
    def recv(self, size: int) -> bytes: ...
    def close(self) -> None: ...


class SSHArmTransport:
    """Socket-like transport through a fixed bridge on the industrial PC."""

    def __init__(self, arm: ArmSettings, remote: RemoteRuntimeSettings) -> None:
        if not remote.enabled or not remote.host.strip() or not remote.user.strip():
            raise ConnectionError("工控机 SSH 连接未配置")
        if not arm.network_interface.strip():
            raise ConnectionError("未配置工控机机械臂专用网口")
        remote_bridge = str(
            PurePosixPath(remote.agent_path).parent / "arm_tcp_bridge.py"
        )
        bridge_command = " ".join(
            shlex.quote(value)
            for value in (
                "/usr/bin/python3",
                remote_bridge,
                "--host", arm.host,
                "--port", str(arm.port),
                "--interface", arm.network_interface,
                "--timeout", str(arm.timeout_s),
            )
        )
        command = [
            "ssh",
            "-T",
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"ConnectTimeout={int(remote.connect_timeout)}",
            "-o", "ServerAliveInterval=5",
            "-o", "ServerAliveCountMax=2",
            "-p", str(remote.port),
            f"{remote.user}@{remote.host}",
            bridge_command,
        ]
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        if self.process.stdin is None or self.process.stdout is None:
            self.close()
            raise ConnectionError("无法创建工控机机械臂隧道")
        self.timeout = arm.timeout_s

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def _failure(self, fallback: str) -> ConnectionError:
        detail = ""
        if self.process.poll() is None:
            try:
                self.process.wait(timeout=0.05)
            except subprocess.TimeoutExpired:
                pass
        if self.process.poll() is not None and self.process.stderr is not None:
            try:
                detail = self.process.stderr.read(8192).decode(errors="replace").strip()
            except OSError:
                pass
        return ConnectionError(detail or fallback)

    def sendall(self, data: bytes) -> None:
        if self.process.poll() is not None or self.process.stdin is None:
            raise self._failure("工控机机械臂隧道已退出")
        view = memoryview(data)
        try:
            while view:
                written = os.write(self.process.stdin.fileno(), view)
                if written <= 0:
                    raise BrokenPipeError("SSH stdin returned a zero-length write")
                view = view[written:]
        except (BrokenPipeError, OSError) as exc:
            raise self._failure(f"工控机机械臂隧道写入失败：{exc}") from exc

    def recv(self, size: int) -> bytes:
        if self.process.stdout is None:
            raise self._failure("工控机机械臂隧道没有输出通道")
        ready, _, _ = select.select([self.process.stdout], [], [], self.timeout)
        if not ready:
            if self.process.poll() is not None:
                raise self._failure("工控机机械臂隧道已退出")
            raise socket.timeout()
        data = os.read(self.process.stdout.fileno(), size)
        if not data:
            raise self._failure("工控机机械臂隧道已断开")
        return data

    def close(self) -> None:
        process = getattr(self, "process", None)
        if process is None:
            return
        try:
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1.0)
        except (OSError, subprocess.SubprocessError):
            pass
        finally:
            for stream in (process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    try:
                        stream.close()
                    except OSError:
                        pass


QUERY_STATES = {
    "get_current_work_frame": "current_work_frame",
    "get_current_tool_frame": "current_tool_frame",
    "get_arm_current_trajectory": "arm_current_trajectory",
    "get_collision_stage": "get_collision_stage",
    "get_current_arm_state": "current_arm_state",
    "get_joint_min_pos": "joint_min_pos",
    "get_joint_max_pos": "joint_max_pos",
}


def finite_vector(value: Any, length: int, name: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise ValueError(f"{name}必须包含 {length} 个数值")
    result: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
            raise ValueError(f"{name}包含无效数值")
        result.append(float(item))
    return result


def segment_intersects_box(
    start: list[float], end: list[float], lower: list[float], upper: list[float]
) -> bool:
    """Return whether a Cartesian line segment enters an axis-aligned box."""
    entry, exit_ = 0.0, 1.0
    for origin, target, low, high in zip(start, end, lower, upper):
        delta = target - origin
        if abs(delta) < 1e-12:
            if origin < low or origin > high:
                return False
            continue
        first, second = (low - origin) / delta, (high - origin) / delta
        entry = max(entry, min(first, second))
        exit_ = min(exit_, max(first, second))
        if entry > exit_:
            return False
    return True


class RealManClient:
    def __init__(
        self,
        arm: ArmSettings,
        gripper: GripperSettings,
        remote: RemoteRuntimeSettings | None = None,
    ) -> None:
        self.arm = arm
        self.gripper = gripper
        self.remote = remote
        self._lock = threading.RLock()
        self._socket: ArmTransport | None = None
        # Hardware access is opt-in. Background state polling must not create a
        # controller connection before an operator explicitly requests it.
        self._connection_enabled = False
        self._buffer = ""
        self._decoder = codecs.getincrementaldecoder("utf-8")()
        self._retry_after = 0.0
        self._last_error = ""
        self._work_frame = ""
        self._work_frame_safe = False
        self._tool_frame = ""
        self._frames_checked_at = 0.0
        self._motion_failed = False

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._socket is not None

    @property
    def connection_enabled(self) -> bool:
        with self._lock:
            return self._connection_enabled

    @property
    def last_error(self) -> str:
        with self._lock:
            return self._last_error

    def _close_locked(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
        self._socket = None
        self._buffer = ""
        self._decoder = codecs.getincrementaldecoder("utf-8")()
        self._work_frame = ""
        self._work_frame_safe = False
        self._tool_frame = ""
        self._frames_checked_at = 0.0
        self._motion_failed = False

    def _connect_locked(self, force: bool = False) -> None:
        if self._socket is not None:
            return
        if not self._connection_enabled:
            raise ConnectionError("机械臂控制链路未连接，请先在 Web 页面点击连接")
        if not self.arm.enabled:
            raise ConnectionError("真机机械臂控制未启用")
        if not force and time.monotonic() < self._retry_after:
            raise ConnectionError(self._last_error or "等待重新连接机械臂")
        candidate: ArmTransport | None = None
        try:
            if self.arm.transport == "industrial_pc":
                if self.remote is None:
                    raise ConnectionError("工控机机械臂隧道配置缺失")
                candidate = SSHArmTransport(self.arm, self.remote)
            else:
                candidate = socket.create_connection(
                    (self.arm.host, self.arm.port), timeout=self.arm.timeout_s
                )
            candidate.settimeout(0.2)
            self._socket = candidate
            self._last_error = ""
        except OSError as exc:
            if candidate is not None:
                candidate.close()
            self._close_locked()
            self._retry_after = time.monotonic() + 2.0
            interface = self.arm.network_interface.strip()
            route = (
                f"（经工控机 {self.remote.host}/{interface}）"
                if self.arm.transport == "industrial_pc" and self.remote is not None
                else ""
            )
            self._last_error = (
                f"无法连接机械臂 {self.arm.host}:{self.arm.port}{route}：{exc}"
            )
            raise ConnectionError(self._last_error) from exc

    def _messages_locked(self) -> list[dict[str, Any]]:
        decoder = json.JSONDecoder()
        messages: list[dict[str, Any]] = []
        self._buffer = self._buffer.lstrip()
        while self._buffer:
            try:
                item, index = decoder.raw_decode(self._buffer)
            except json.JSONDecodeError:
                break
            self._buffer = self._buffer[index:].lstrip()
            if isinstance(item, dict):
                messages.append(item)
                if (
                    item.get("state") == "current_trajectory_state"
                    and item.get("device", 0) == 0
                    and item.get("trajectory_state") is False
                ):
                    self._motion_failed = True
                if (
                    item.get("state") == "joint_state"
                    and "arm_err" in item
                    and not self._error_free(item["arm_err"])
                ):
                    self._motion_failed = True
        return messages

    def _request_locked(
        self,
        payload: dict[str, Any],
        match: Callable[[dict[str, Any]], bool] | None = None,
        force_connect: bool = False,
    ) -> dict[str, Any]:
        self._connect_locked(force_connect)
        assert self._socket is not None
        command = str(payload["command"])
        state_alias = QUERY_STATES.get(command)
        matcher = match or (
            lambda item: item.get("command") == command
            or (state_alias is not None and item.get("state") == state_alias)
        )
        self._messages_locked()
        try:
            packet = json.dumps(payload, separators=(",", ":")) + "\r\n"
            self._socket.sendall(packet.encode("utf-8"))
            deadline = time.monotonic() + self.arm.timeout_s
            while time.monotonic() < deadline:
                self._socket.settimeout(min(0.1, max(0.01, deadline - time.monotonic())))
                try:
                    data = self._socket.recv(8192)
                except socket.timeout:
                    continue
                if not data:
                    raise ConnectionError("机械臂控制器已断开连接")
                self._buffer += self._decoder.decode(data)
                if len(self._buffer) > 1024 * 1024:
                    raise ValueError("机械臂控制器消息过长或不是有效 JSON")
                candidates = [item for item in self._messages_locked() if matcher(item)]
                if candidates:
                    return candidates[-1]
            raise TimeoutError(f"等待机械臂指令 {command} 回复超时")
        except (OSError, ConnectionError, TimeoutError, UnicodeError, ValueError) as exc:
            self._last_error = str(exc)
            self._retry_after = time.monotonic() + 1.0
            self._close_locked()
            raise

    def _ack_locked(self, payload: dict[str, Any], field: str) -> dict[str, Any]:
        response = self._request_locked(payload, force_connect=True)
        if response.get(field) is not True:
            raise RuntimeError(f"控制器拒绝 {payload['command']}：{response}")
        return response

    @staticmethod
    def _error_free(value: Any) -> bool:
        return (type(value) is int and value == 0) or (
            isinstance(value, list)
            and bool(value)
            and all(type(code) is int and code == 0 for code in value)
        )

    def _arm_state_locked(self) -> dict[str, Any]:
        response = self._request_locked({"command": "get_current_arm_state"})
        state = response.get("arm_state", {})
        if not isinstance(state, dict) or not self._error_free(state.get("err")):
            errors = state.get("err") if isinstance(state, dict) else state
            codes = errors if isinstance(errors, list) else [errors]
            detail = "；检测到碰撞，请在示教器检查并清除报警" if 4109 in codes else ""
            raise RuntimeError(f"机械臂控制器报警：{errors}{detail}")
        if self._motion_failed:
            raise RuntimeError("机械臂控制器报告轨迹执行失败")
        return state

    def _tool_frame_locked(self) -> str:
        response = self._request_locked({"command": "get_current_tool_frame"})
        name = response.get("tool_name")
        if not isinstance(name, str):
            raise ValueError("控制器未返回有效工具坐标系")
        self._tool_frame = name
        return name

    def _frames_locked(self, force: bool = False) -> tuple[str, bool, str]:
        if (
            not force
            and self._tool_frame
            and time.monotonic() - self._frames_checked_at < 1.0
        ):
            return self._work_frame, self._work_frame_safe, self._tool_frame
        work = self._request_locked({"command": "get_current_work_frame"})
        pose = finite_vector(work.get("pose"), 6, "工作坐标系")
        name = work.get("frame_name")
        if not isinstance(name, str):
            raise ValueError("控制器未返回有效工作坐标系")
        tool = self._tool_frame_locked()
        self._work_frame = name
        self._work_frame_safe = name == "Base" and not any(abs(value) > 0 for value in pose)
        self._frames_checked_at = time.monotonic()
        return self._work_frame, self._work_frame_safe, tool

    def _validate_frames_locked(self) -> str:
        work, safe, tool = self._frames_locked(force=True)
        if not safe:
            raise ArmMotionDisabled("当前工作坐标系不是零偏移 Base，禁止 Web 运动")
        expected = self.arm.expected_tool.strip()
        if expected and tool != expected:
            raise ArmMotionDisabled(f"当前工具系为 {tool}，要求使用 {expected}")
        return tool

    def _configure_collision_locked(self) -> None:
        level = self.arm.collision_level
        self._ack_locked(
            {"command": "set_collision_stage", "collision_stage": level},
            "collision_state",
        )
        response = self._request_locked({"command": "get_collision_stage"})
        if response.get("collision_stage") != level:
            raise ArmMotionDisabled(
                f"碰撞检测等级未确认：要求 {level}，控制器返回 {response.get('collision_stage')}"
            )

    def _trajectory_locked(self) -> str:
        response = self._request_locked({"command": "get_arm_current_trajectory"})
        trajectory_type = response.get("type")
        if not isinstance(trajectory_type, str):
            raise ValueError("控制器未返回有效轨迹状态")
        if self._motion_failed:
            raise RuntimeError("机械臂控制器报告轨迹执行失败")
        return trajectory_type

    def _require_stationary_locked(self) -> None:
        if self._trajectory_locked() != "none":
            raise ArmMotionDisabled("机械臂仍在运动，请先停止或等待当前轨迹完成")

    def _require_motion_locked(self) -> None:
        if not self.arm.allow_motion_commands:
            raise ArmMotionDisabled("真机机械臂运动指令已被配置锁定")
        self._require_stationary_locked()
        self._validate_frames_locked()
        self._configure_collision_locked()

    def _joint_limits_locked(self) -> tuple[list[float], list[float]]:
        lower = self._request_locked({"command": "get_joint_min_pos"})
        upper = self._request_locked({"command": "get_joint_max_pos"})
        low = [value / 1000.0 for value in finite_vector(lower.get("min_pos"), 6, "关节下限")]
        high = [value / 1000.0 for value in finite_vector(upper.get("max_pos"), 6, "关节上限")]
        if any(a >= b for a, b in zip(low, high)):
            raise ValueError("控制器返回的关节限位无效")
        return low, high

    def _snapshot_sync(self) -> ArmState:
        with self._lock:
            state = self._arm_state_locked()
            joints = [value / 1000.0 for value in finite_vector(state.get("joint"), 6, "关节角")]
            raw_pose = finite_vector(state.get("pose"), 6, "末端位姿")
            trajectory_type = self._trajectory_locked()
            work, work_safe, tool = self._frames_locked()
            return ArmState(
                connected=True,
                moving=trajectory_type != "none",
                joints=joints,
                pose=Pose(
                    x=raw_pose[0] / 1e6,
                    y=raw_pose[1] / 1e6,
                    z=raw_pose[2] / 1e6,
                    rx=raw_pose[3] / 1e3,
                    ry=raw_pose[4] / 1e3,
                    rz=raw_pose[5] / 1e3,
                ),
                work_frame=work,
                work_frame_safe=work_safe,
                tool_frame=tool,
            )

    async def snapshot(self) -> ArmState:
        return await asyncio.to_thread(self._snapshot_sync)

    def _enable_connection_sync(self) -> None:
        with self._lock:
            self._connection_enabled = True
            # An explicit operator action is allowed to retry immediately,
            # regardless of the backoff left by a previous failed attempt.
            self._retry_after = 0.0

    async def enable_connection(self) -> None:
        await asyncio.to_thread(self._enable_connection_sync)

    def _disable_connection_sync(self) -> None:
        with self._lock:
            self._connection_enabled = False
            self._close_locked()

    async def disable_connection(self) -> None:
        await asyncio.to_thread(self._disable_connection_sync)

    def _move_joints_sync(self, positions: list[float], speed: int) -> None:
        target = finite_vector(positions, 6, "关节目标")
        with self._lock:
            self._require_motion_locked()
            low, high = self._joint_limits_locked()
            for index, value in enumerate(target):
                if not low[index] <= value <= high[index]:
                    raise ArmMotionDisabled(
                        f"J{index + 1} 目标 {value:.3f}° 超出控制器限位 {low[index]:.3f}°～{high[index]:.3f}°"
                    )
            self._motion_failed = False
            self._ack_locked(
                {
                    "command": "movej",
                    "joint": [int(round(value * 1000)) for value in target],
                    "v": speed,
                    "r": 0,
                    "trajectory_connect": 0,
                },
                "receive_state",
            )
            if self._motion_failed:
                raise RuntimeError("机械臂控制器报告轨迹执行失败")

    async def move_joints(self, positions: list[float], speed: int) -> None:
        await self._run_command(self._move_joints_sync, positions, speed)

    async def move_joint(self, joint: int, position: float, speed: int) -> None:
        try:
            snapshot = await self.snapshot()
            target = list(snapshot.joints)
            target[joint - 1] = position
            await self.move_joints(target, speed)
        except (ArmMotionDisabled, RealManControllerError):
            raise
        except (ConnectionError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
            raise RealManControllerError(str(exc)) from exc

    def _move_pose_sync(self, pose: Pose, speed: int) -> None:
        values = [pose.x, pose.y, pose.z, pose.rx, pose.ry, pose.rz]
        finite_vector(values, 6, "末端位姿")
        lower = finite_vector(self.arm.workspace_min_m, 3, "工作空间下限")
        upper = finite_vector(self.arm.workspace_max_m, 3, "工作空间上限")
        clearance = self.arm.clearance_m
        for axis, value, low, high in zip("XYZ", values[:3], lower, upper):
            if not low + clearance <= value <= high - clearance:
                raise ArmMotionDisabled(
                    f"{axis} 目标 {value * 1000:.1f} mm 超出安全工作空间"
                )
        with self._lock:
            self._require_motion_locked()
            current = self._arm_state_locked()
            current_pose = finite_vector(current.get("pose"), 6, "当前末端位姿")
            start = [value / 1e6 for value in current_pose[:3]]
            target = values[:3]
            distance = math.sqrt(sum((b - a) ** 2 for a, b in zip(start, target)))
            if distance > self.arm.max_pose_segment_m:
                raise ArmMotionDisabled(
                    f"本次 TCP 直线运动 {distance * 1000:.1f} mm 超过单段上限 "
                    f"{self.arm.max_pose_segment_m * 1000:.1f} mm"
                )
            if self.arm.keepout_enabled:
                keepout_low = [
                    value - clearance
                    for value in finite_vector(self.arm.keepout_min_m, 3, "禁止区域下限")
                ]
                keepout_high = [
                    value + clearance
                    for value in finite_vector(self.arm.keepout_max_m, 3, "禁止区域上限")
                ]
                if segment_intersects_box(start, target, keepout_low, keepout_high):
                    raise ArmMotionDisabled("TCP 直线路径进入配置的 Base 坐标禁止区域")
            raw = [
                int(round(pose.x * 1e6)), int(round(pose.y * 1e6)), int(round(pose.z * 1e6)),
                int(round(pose.rx * 1e3)), int(round(pose.ry * 1e3)), int(round(pose.rz * 1e3)),
            ]
            self._motion_failed = False
            self._ack_locked(
                {"command": "movel", "pose": raw, "v": speed, "r": 0, "trajectory_connect": 0},
                "receive_state",
            )
            if self._motion_failed:
                raise RuntimeError("机械臂控制器报告轨迹执行失败")

    async def move_pose(self, pose: Pose, speed: int) -> None:
        await self._run_command(self._move_pose_sync, pose, speed)

    def _stop_sync(self) -> None:
        with self._lock:
            self._connect_locked(force=True)
            self._ack_locked({"command": "set_arm_stop"}, "arm_stop")
            self._motion_failed = False

    async def stop_arm(self) -> None:
        await self._run_command(self._stop_sync)

    def _set_io_locked(self, channel: int, value: int) -> None:
        self._ack_locked(
            {"command": "set_tool_DO_state", "IO_Num": channel, "state": value},
            "set_state",
        )

    def _release_outputs_locked(self) -> None:
        inactive = 1 - self.gripper.active_level
        self._set_io_locked(self.gripper.open_io, inactive)
        self._set_io_locked(self.gripper.close_io, inactive)

    def _gripper_pulse_sync(self, action: str) -> None:
        if not self.gripper.enabled or not self.gripper.allow_commands:
            raise ArmMotionDisabled("真机夹爪输出已被配置锁定")
        channel = self.gripper.open_io if action == "open" else self.gripper.close_io
        opposite = self.gripper.close_io if action == "open" else self.gripper.open_io
        with self._lock:
            self._connect_locked(force=True)
            self._require_stationary_locked()
            for item in (self.gripper.open_io, self.gripper.close_io):
                self._ack_locked(
                    {"command": "set_tool_IO_mode", "IO_Num": item, "state": 1},
                    "set_state",
                )
            inactive = 1 - self.gripper.active_level
            self._set_io_locked(opposite, inactive)
            try:
                self._set_io_locked(channel, self.gripper.active_level)
                time.sleep(self.gripper.pulse_s)
            finally:
                self._release_outputs_locked()

    async def gripper_pulse(self, action: str) -> None:
        await self._run_command(self._gripper_pulse_sync, action)

    def _stop_gripper_sync(self) -> None:
        with self._lock:
            if not self.gripper.enabled:
                return
            self._connect_locked(force=True)
            self._release_outputs_locked()

    async def stop_gripper(self) -> None:
        await self._run_command(self._stop_gripper_sync)

    async def _run_command(self, operation: Callable[..., None], *args: Any) -> None:
        try:
            await asyncio.to_thread(operation, *args)
        except ArmMotionDisabled:
            raise
        except (ConnectionError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
            raise RealManControllerError(str(exc)) from exc

    async def close(self) -> None:
        await self.disable_connection()


class RealManArmController(ArmController):
    def __init__(self, client: RealManClient, settings: ArmSettings) -> None:
        self.client = client
        self.settings = settings
        self._state = ArmState()

    async def connect(self) -> None:
        await self.client.enable_connection()
        try:
            self._state = await self.client.snapshot()
        except Exception as exc:
            await self.client.disable_connection()
            self._state = ArmState(error=str(exc))
            if isinstance(exc, ArmMotionDisabled):
                raise
            raise RealManControllerError(str(exc)) from exc

    async def disconnect(self) -> None:
        if self._state.moving:
            raise ArmMotionDisabled("机械臂正在运动，请先停止后再断开控制链路")
        await self.client.disable_connection()
        self._state = ArmState(error="控制链路已手动断开")

    def _speed(self, value: int | None, default: int) -> int:
        speed = default if value is None else value
        if isinstance(speed, bool) or not 1 <= int(speed) <= 100:
            raise ValueError("机械臂速度必须为 1～100 的整数百分比")
        return int(speed)

    async def move_joint(self, joint: int, position: float, speed: int | None = None) -> None:
        await self.client.move_joint(joint, position, self._speed(speed, self.settings.joint_speed_percent))
        self._state.moving = True

    async def move_joints(self, positions: list[float], speed: int | None = None) -> None:
        await self.client.move_joints(positions, self._speed(speed, self.settings.joint_speed_percent))
        self._state.moving = True

    async def move_pose(self, pose: Pose, speed: int | None = None) -> None:
        await self.client.move_pose(pose, self._speed(speed, self.settings.pose_speed_percent))
        self._state.moving = True

    async def stop(self) -> None:
        if not self.client.connection_enabled:
            self._state.moving = False
            return
        await self.client.stop_arm()
        self._state.moving = False

    async def get_joint_state(self) -> list[float]:
        return (await self.get_state()).joints

    async def get_pose(self) -> Pose:
        return (await self.get_state()).pose

    async def get_state(self) -> ArmState:
        if not self.client.connection_enabled:
            self._state.connected = False
            self._state.moving = False
            if not self._state.error:
                self._state.error = "等待在 Web 页面手动连接机械臂"
            return self._state.model_copy(deep=True)
        try:
            self._state = await self.client.snapshot()
        except Exception as exc:
            # A broken hardware link returns to the manual-connect state. This
            # prevents the background poller from repeatedly opening SSH/TCP
            # sessions without a fresh operator action.
            await self.client.disable_connection()
            self._state.connected = False
            self._state.moving = False
            self._state.error = str(exc)
        return self._state.model_copy(deep=True)

    async def is_connected(self) -> bool:
        return (await self.get_state()).connected


class RealManGripperController(GripperController):
    def __init__(self, client: RealManClient) -> None:
        self.client = client
        self._state = GripperState(status="stopped")

    async def open(self) -> None:
        self._state.moving = True
        try:
            await self.client.gripper_pulse("open")
            self._state.status = "opened"
            self._state.position = 1.0
        finally:
            self._state.moving = False

    async def close(self) -> None:
        self._state.moving = True
        try:
            await self.client.gripper_pulse("close")
            self._state.status = "closed"
            self._state.position = 0.0
        finally:
            self._state.moving = False

    async def stop(self) -> None:
        if not self.client.connection_enabled:
            self._state.status = "stopped"
            self._state.moving = False
            return
        await self.client.stop_gripper()
        self._state.status = "stopped"
        self._state.moving = False

    async def set_position(self, position: float) -> None:
        if position >= 0.5:
            await self.open()
        else:
            await self.close()

    async def set_force(self, force: float) -> None:
        raise NotImplementedError("当前 IO 夹爪不支持力控制")

    async def get_state(self) -> GripperState:
        state = deepcopy(self._state)
        state.connected = self.client.connected and self.client.gripper.enabled
        return state

    async def is_connected(self) -> bool:
        return self.client.connected and self.client.gripper.enabled
