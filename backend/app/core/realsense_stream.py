"""RealSense color capture and shared MJPEG streaming for Web clients.

This service never synthesizes frames. Device discovery, capture and JPEG
encoding run in one background thread so ROS2/FastAPI event loops stay free.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from io import BytesIO
import os
from pathlib import Path
import select
import shlex
import struct
import subprocess
import threading
import time
from typing import AsyncIterator

from app.core.config import RealSenseSettings, RemoteRuntimeSettings
from app.models.visualization import CameraStreamStatus


class RealSenseStream:
    boundary = b"frame"

    def __init__(
        self,
        settings: RealSenseSettings,
        remote: RemoteRuntimeSettings | None = None,
    ) -> None:
        self.settings = settings
        self.remote = remote
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._service_started = False
        self._stream_clients = 0
        self._jpeg: bytes | None = None
        self._status = CameraStreamStatus(
            enabled=settings.enabled,
            source=settings.source,
            width=settings.width,
            height=settings.height,
            fps=settings.fps,
        )

    async def start(self) -> None:
        if not self.settings.enabled:
            return
        # Do not open the camera or an SSH/FFmpeg pipeline at backend startup.
        # Capture starts only when a browser actually requests the MJPEG URL.
        with self._condition:
            self._service_started = True

    def _start_capture_locked(self) -> None:
        """Start one capture worker; caller holds ``_condition``."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="realsense-web-stream",
            daemon=True,
        )
        self._thread.start()

    def _acquire_stream(self) -> None:
        with self._condition:
            if not self.settings.enabled or not self._service_started:
                raise RuntimeError("RealSense 视频服务未启动")
            self._stream_clients += 1
            self._start_capture_locked()

    def _release_stream(self) -> None:
        with self._condition:
            self._stream_clients = max(0, self._stream_clients - 1)
            if self._stream_clients == 0:
                # The worker terminates the remote FFmpeg/SSH process. It will
                # be recreated if a browser opens the camera again.
                self._stop.set()
                self._condition.notify_all()

    async def stop(self) -> None:
        with self._condition:
            self._service_started = False
            self._stream_clients = 0
            self._stop.set()
            self._condition.notify_all()
        thread, self._thread = self._thread, None
        if thread is not None:
            await asyncio.to_thread(thread.join, 3.0)
        self._update_status(connected=False)

    def status(self) -> CameraStreamStatus:
        with self._condition:
            return self._status.model_copy(deep=True)

    def _update_status(self, **updates: object) -> None:
        with self._condition:
            if updates.get("connected") is False:
                self._jpeg = None
            payload = self._status.model_dump()
            payload.update(updates)
            payload["updated_at"] = datetime.now(timezone.utc)
            self._status = CameraStreamStatus.model_validate(payload)
            self._condition.notify_all()

    def _publish(self, jpeg: bytes, serial: str) -> None:
        with self._condition:
            self._jpeg = jpeg
            payload = self._status.model_dump()
            payload.update(
                connected=True,
                serial=serial,
                sequence=self._status.sequence + 1,
                error="",
                updated_at=datetime.now(timezone.utc),
            )
            self._status = CameraStreamStatus.model_validate(payload)
            self._condition.notify_all()

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    if self.settings.source == "industrial_pc":
                        self._capture_remote()
                    else:
                        self._capture_local()
                except Exception as exc:
                    self._update_status(connected=False, error=f"RealSense：{exc}")
                if not self._stop.is_set():
                    self._stop.wait(self.settings.retry_interval_s)
        finally:
            with self._condition:
                if self._thread is threading.current_thread():
                    self._thread = None
                restart = self._service_started and self._stream_clients > 0
                if restart:
                    self._start_capture_locked()
            # A successor has already started for a newly connected browser;
            # do not overwrite its fresh connected status with this worker's
            # teardown notification.
            if not restart:
                self._update_status(connected=False)

    def _capture_local(self) -> None:
        try:
            import numpy as np
            from PIL import Image
            import pyrealsense2 as rs
        except ImportError as exc:
            raise RuntimeError(
                "缺少 pyrealsense2、numpy 或 Pillow；请重新安装后端真机依赖"
            ) from exc

        pipeline = rs.pipeline()
        stream = rs.config()
        if self.settings.serial.strip():
            stream.enable_device(self.settings.serial.strip())
        stream.enable_stream(
            rs.stream.color,
            self.settings.width,
            self.settings.height,
            rs.format.rgb8,
            self.settings.fps,
        )
        started = False
        try:
            profile = pipeline.start(stream)
            started = True
            device = profile.get_device()
            serial = device.get_info(rs.camera_info.serial_number)
            self._update_status(connected=True, serial=serial, error="")
            missed = 0
            while not self._stop.is_set():
                ok, frames = pipeline.try_wait_for_frames(1000)
                if not ok:
                    missed += 1
                    if missed >= 5:
                        raise TimeoutError("连续 5 秒未收到彩色帧")
                    continue
                color = frames.get_color_frame()
                if not color:
                    continue
                missed = 0
                image = np.asanyarray(color.get_data())
                output = BytesIO()
                Image.fromarray(image).save(
                    output,
                    format="JPEG",
                    quality=self.settings.jpeg_quality,
                    optimize=False,
                )
                self._publish(output.getvalue(), serial)
        finally:
            if started:
                pipeline.stop()

    def _capture_remote(self) -> None:
        remote = self.remote
        if (
            remote is None
            or not remote.enabled
            or not remote.host.strip()
            or not remote.user.strip()
        ):
            raise RuntimeError("工控机 SSH 连接未配置")

        # The helper retains the newest local FFmpeg frame, but it writes one
        # response only after this worker requests it. Unlike a continuous
        # MJPEG pipe, TCP therefore cannot queue a backlog of obsolete frames.
        relay_path = str(Path(remote.agent_path).parent / "camera_relay.py")
        relay = [
            "/usr/bin/python3", relay_path,
            "--video-device", self.settings.video_device,
            "--input-format", self.settings.input_format,
            "--width", str(self.settings.width),
            "--height", str(self.settings.height),
            "--fps", str(self.settings.fps),
            "--jpeg-quality", str(self.settings.jpeg_quality),
            "--max-frame-bytes", str(self.settings.max_frame_bytes),
        ]
        remote_command = " ".join(shlex.quote(argument) for argument in relay)
        command = [
            "ssh",
            "-T",
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"ConnectTimeout={int(remote.connect_timeout)}",
            # Small preview frames are latency-sensitive.  Explicitly avoid
            # SSH compression work and request low-delay IP classification;
            # the JPEG stream is already compressed.
            "-o", "Compression=no",
            "-o", "IPQoS=lowdelay",
            "-o", "ServerAliveInterval=5",
            "-o", "ServerAliveCountMax=2",
            "-p", str(remote.port),
            f"{remote.user}@{remote.host}",
            remote_command,
        ]
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        if process.stdin is None or process.stdout is None:
            process.terminate()
            raise RuntimeError("无法创建工控机视频通道")

        output_fd = process.stdout.fileno()
        label = self.settings.serial.strip() or f"{remote.host}:{self.settings.video_device}"
        try:
            empty_since: float | None = None
            while not self._stop.is_set():
                process.stdin.write(b"N")
                process.stdin.flush()
                header = self._read_remote_bytes(process, output_fd, 4)
                frame_size = struct.unpack("!I", header)[0]
                if frame_size == 0:
                    # The helper has not received its first camera frame yet.
                    # Avoid a hot retry loop while retaining a live connection.
                    empty_since = empty_since or time.monotonic()
                    if time.monotonic() - empty_since > 5.0:
                        raise RuntimeError("工控机最新帧中继 5 秒未收到相机画面")
                    self._stop.wait(0.05)
                    continue
                empty_since = None
                if frame_size > self.settings.max_frame_bytes:
                    raise RuntimeError("工控机返回的视频帧超过大小限制")
                jpeg = self._read_remote_bytes(process, output_fd, frame_size)
                if not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
                    raise RuntimeError("工控机返回的不是完整 JPEG 帧")
                self._publish(jpeg, label)

            if not self._stop.is_set():
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    pass
                detail = ""
                if process.poll() is not None and process.stderr is not None:
                    detail = process.stderr.read(8192).decode(errors="replace").strip()
                raise RuntimeError(detail or "工控机 RealSense 视频通道已断开")
        finally:
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()
            if process.poll() is None:
                try:
                    # EOF is the normal shutdown signal for the private
                    # request/response protocol and lets the IPC helper reap
                    # its own FFmpeg child before we escalate.
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=1.0)
            for stream in (process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    stream.close()

    def _read_remote_bytes(
        self, process: subprocess.Popen[bytes], output_fd: int, size: int
    ) -> bytes:
        """Read one demand-response field without blocking shutdown forever."""
        data = bytearray()
        while len(data) < size:
            ready, _, _ = select.select([output_fd], [], [], 0.5)
            if not ready:
                if self._stop.is_set():
                    raise RuntimeError("视频流已停止")
                if process.poll() is not None:
                    raise RuntimeError("工控机最新帧服务已断开")
                continue
            chunk = os.read(output_fd, size - len(data))
            if not chunk:
                raise RuntimeError("工控机最新帧服务已断开")
            data.extend(chunk)
        return bytes(data)

    def wait_for_frame(self, after: int, timeout: float = 2.0) -> tuple[int, bytes] | None:
        deadline = time.monotonic() + timeout
        with self._condition:
            while not self._stop.is_set():
                if self._jpeg is not None and self._status.sequence > after:
                    return self._status.sequence, self._jpeg
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)
        return None

    async def mjpeg(self) -> AsyncIterator[bytes]:
        self._acquire_stream()
        sequence = -1
        try:
            while not self._stop.is_set():
                item = await asyncio.to_thread(self.wait_for_frame, sequence)
                if item is None:
                    continue
                sequence, jpeg = item
                yield (
                    b"--" + self.boundary + b"\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(jpeg)).encode("ascii") + b"\r\n\r\n"
                    + jpeg
                    + b"\r\n"
                )
        finally:
            self._release_stream()
