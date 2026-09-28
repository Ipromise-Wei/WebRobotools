#!/usr/bin/env python3
"""Serve only the newest V4L2 JPEG frame over an SSH stdin/stdout protocol.

This process deliberately has no listening socket.  It is started by the Web
server through its already authenticated SSH connection.  The capture thread
continuously drains FFmpeg locally on the industrial PC, while the SSH stdout
side sends a frame only after the Web server writes one ``N`` request byte.
That demand-driven design prevents TCP from queueing old MJPEG frames.
"""

from __future__ import annotations

import argparse
import os
import struct
import subprocess
import sys
import threading
import time


def extract_latest_complete_jpeg(buffer: bytearray, maximum_bytes: int) -> bytes | None:
    latest: bytes | None = None
    while True:
        start = buffer.find(b"\xff\xd8")
        if start < 0:
            if len(buffer) > 1:
                del buffer[:-1]
            return latest
        end = buffer.find(b"\xff\xd9", start + 2)
        if end < 0:
            if start:
                del buffer[:start]
            if len(buffer) > 16 * 1024 * 1024:
                raise RuntimeError("camera frame exceeds parser limit")
            return latest
        jpeg = bytes(buffer[start:end + 2])
        del buffer[:end + 2]
        if len(jpeg) <= maximum_bytes:
            latest = jpeg


class LatestFrameRelay:
    def __init__(self, options: argparse.Namespace) -> None:
        self.options = options
        self._condition = threading.Condition()
        self._latest: bytes | None = None
        self._error = ""
        self._closed = False
        self._process: subprocess.Popen[bytes] | None = None
        self._reader: threading.Thread | None = None

    def _ffmpeg_command(self) -> list[str]:
        quality = max(2, min(31, round((100 - self.options.jpeg_quality) / 4) + 2))
        return [
            "/usr/bin/ffmpeg",
            "-hide_banner", "-loglevel", "error", "-nostdin",
            "-fflags", "nobuffer", "-flags", "low_delay", "-thread_queue_size", "1",
            "-f", "v4l2",
            "-input_format", self.options.input_format,
            "-video_size", f"{self.options.width}x{self.options.height}",
            "-framerate", str(self.options.fps),
            "-i", self.options.video_device,
            "-an", "-c:v", "mjpeg", "-q:v", str(quality),
            "-f", "image2pipe", "-flush_packets", "1", "pipe:1",
        ]

    def start(self) -> None:
        self._process = subprocess.Popen(
            self._ffmpeg_command(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        if self._process.stdout is None:
            raise RuntimeError("could not open FFmpeg output")
        self._reader = threading.Thread(target=self._read_frames, daemon=True)
        self._reader.start()

    def _read_frames(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        buffer = bytearray()
        try:
            while not self._closed:
                chunk = os.read(process.stdout.fileno(), 262_144)
                if not chunk:
                    break
                buffer.extend(chunk)
                latest = extract_latest_complete_jpeg(buffer, self.options.max_frame_bytes)
                if latest is not None:
                    with self._condition:
                        self._latest = latest
                        self._condition.notify_all()
            if not self._closed:
                detail = ""
                if process.stderr is not None:
                    detail = process.stderr.read(8192).decode(errors="replace").strip()
                self._error = detail or "FFmpeg video capture ended"
        except Exception as exc:
            self._error = str(exc)
        finally:
            with self._condition:
                self._condition.notify_all()

    def latest_frame(self, timeout: float = 2.0) -> bytes | None:
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._latest is None and not self._error and not self._closed:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)
            return self._latest

    def close(self) -> None:
        self._closed = True
        with self._condition:
            self._condition.notify_all()
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
        if self._reader is not None:
            self._reader.join(timeout=1)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-device", required=True)
    parser.add_argument("--input-format", choices=("yuyv422", "mjpeg"), required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--fps", type=int, required=True)
    parser.add_argument("--jpeg-quality", type=int, required=True)
    parser.add_argument("--max-frame-bytes", type=int, required=True)
    return parser.parse_args()


def main() -> int:
    relay = LatestFrameRelay(arguments())
    relay.start()
    output = sys.stdout.buffer
    try:
        while True:
            request = sys.stdin.buffer.read(1)
            if not request:
                return 0
            if request != b"N":
                continue
            frame = relay.latest_frame()
            output.write(struct.pack("!I", len(frame) if frame is not None else 0))
            if frame is not None:
                output.write(frame)
            output.flush()
    except BrokenPipeError:
        return 0
    finally:
        relay.close()


if __name__ == "__main__":
    raise SystemExit(main())
