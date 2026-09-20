#!/usr/bin/env python3
"""Industrial-PC stdio bridge for one allow-listed robot-arm TCP connection."""

from __future__ import annotations

import argparse
import fcntl
import os
import selectors
import socket
import struct
import subprocess
import sys


def interface_ipv4(name: str) -> str:
    try:
        socket.if_nametoindex(name)
    except OSError as exc:
        raise RuntimeError(f"工控机网口 {name} 不存在") from exc
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        request = struct.pack("256s", name.encode("utf-8")[:15])
        return socket.inet_ntoa(fcntl.ioctl(probe.fileno(), 0x8915, request)[20:24])
    except OSError as exc:
        raise RuntimeError(f"工控机网口 {name} 未启用或没有 IPv4 地址") from exc
    finally:
        probe.close()


def require_route(host: str, interface: str, source_ip: str) -> None:
    result = subprocess.run(
        ["ip", "route", "get", host],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=3,
    )
    route = result.stdout.strip()
    if result.returncode or f" dev {interface} " not in f" {route} ":
        detail = result.stderr.strip() or route or "没有可用路由"
        raise RuntimeError(f"到 {host} 的路由未经过 {interface}：{detail}")
    if " src " in f" {route} " and f" src {source_ip} " not in f" {route} ":
        raise RuntimeError(f"{interface} 路由源地址与网口地址不一致：{route}")


def connect_arm(host: str, port: int, interface: str, timeout: float) -> socket.socket:
    source_ip = interface_ipv4(interface)
    require_route(host, interface, source_ip)
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        connection.settimeout(timeout)
        bind_option = getattr(socket, "SO_BINDTODEVICE", None)
        if bind_option is not None:
            try:
                connection.setsockopt(
                    socket.SOL_SOCKET,
                    bind_option,
                    interface.encode("utf-8") + b"\0",
                )
            except PermissionError:
                # The source bind plus the verified kernel route still prevents
                # falling back to another interface for this destination.
                pass
        connection.bind((source_ip, 0))
        connection.connect((host, port))
        connection.settimeout(None)
        return connection
    except Exception:
        connection.close()
        raise


def relay(connection: socket.socket) -> None:
    selector = selectors.DefaultSelector()
    selector.register(sys.stdin.buffer, selectors.EVENT_READ, "stdin")
    selector.register(connection, selectors.EVENT_READ, "socket")
    try:
        while True:
            for key, _ in selector.select(timeout=1.0):
                if key.data == "stdin":
                    data = os.read(sys.stdin.fileno(), 65536)
                    if not data:
                        return
                    connection.sendall(data)
                else:
                    data = connection.recv(65536)
                    if not data:
                        return
                    output = memoryview(data)
                    while output:
                        written = os.write(sys.stdout.fileno(), output)
                        if written <= 0:
                            raise BrokenPipeError("Web 后端连接已关闭")
                        output = output[written:]
    finally:
        selector.close()
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--interface", required=True)
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        raise ValueError("机械臂端口无效")
    relay(connect_arm(args.host, args.port, args.interface, args.timeout))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"arm bridge: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
