#!/usr/bin/env python3
"""Launch installed Nav2 with its final velocity routed into WebRobot's watchdog.

The installed Humble launch file owns the rest of Nav2's wiring. Refuse to
start if its expected smoother remapping changes instead of risking a second
publisher directly on the chassis driver's /cmd_vel topic.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tempfile

from ament_index_python.packages import get_package_share_directory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--params-file", required=True)
    options = parser.parse_args()
    source = Path(get_package_share_directory("nav2_bringup")) / "launch/navigation_launch.py"
    original = source.read_text(encoding="utf-8")
    old = "('cmd_vel_smoothed', 'cmd_vel')"
    new = "('cmd_vel_smoothed', '/webrobot/nav_cmd_vel')"
    behavior_blocks = (
        ("package='nav2_behaviors',\n                executable='behavior_server',", "remappings=remappings),"),
        ("package='nav2_behaviors',\n                plugin='behavior_server::BehaviorServer',", "remappings=remappings),"),
    )
    if original.count(old) != 2:
        raise RuntimeError("Nav2 速度平滑器启动配置与预期不符；已拒绝启动")
    patched = original.replace(old, new)
    for prefix, remapping in behavior_blocks:
        start = patched.find(prefix)
        if start < 0 or patched.find(prefix, start + 1) >= 0:
            raise RuntimeError("Nav2 恢复动作启动配置与预期不符；已拒绝启动")
        end = patched.find(remapping, start)
        next_node = patched.find("            Node(", start + len(prefix))
        next_component = patched.find("            ComposableNode(", start + len(prefix))
        boundaries = [position for position in (next_node, next_component) if position >= 0]
        if end < 0 or (boundaries and end > min(boundaries)):
            raise RuntimeError("Nav2 恢复动作速度出口未识别；已拒绝启动")
        patched = patched[:end] + "remappings=remappings + [('cmd_vel', 'cmd_vel_nav')])," + patched[end + len(remapping):]
    with tempfile.TemporaryDirectory(prefix="webrobot-nav2-") as directory:
        launch_file = Path(directory) / "navigation_launch.py"
        launch_file.write_text(patched, encoding="utf-8")
        command = [
            "ros2", "launch", str(launch_file),
            "use_sim_time:=False", "autostart:=True", "use_composition:=False",
            f"params_file:={options.params_file}",
        ]
        return subprocess.call(command, env=os.environ.copy())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        raise SystemExit(f"WebRobot Nav2: {exc}") from exc
