#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "start_system_ros2.sh is retained for compatibility; start_system.sh now detects ROS2 mode automatically."
exec "$project_dir/scripts/start_system.sh"
