#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config_file="$project_dir/backend/config/config.yaml"
robot_mode="$(awk '/^robot:/{found=1; next} found && /^  mode:/{print $2; exit} found && /^[^ ]/{exit}' "$config_file")"
reload_args=(--reload)

if [[ "$robot_mode" == "ros2" ]]; then
  if [[ ! -f /opt/ros/humble/setup.bash ]]; then
    echo "ROS2 Humble was not found at /opt/ros/humble." >&2
    exit 1
  fi
  # ROS2 environment hooks legitimately inspect variables before defining them,
  # which is incompatible with Bash nounset mode.
  set +u
  source /opt/ros/humble/setup.bash
  set -u
  export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-30}"
  reload_args=()

  ros_venv="$project_dir/backend/.venv-ros2/bin/python"
  if [[ -x "$ros_venv" ]] && "$ros_venv" -c 'import rclpy, fastapi, uvicorn' >/dev/null 2>&1; then
    python_bin="$ros_venv"
  elif [[ -x /usr/bin/python3.10 ]] && /usr/bin/python3.10 -c 'import rclpy, fastapi, uvicorn' >/dev/null 2>&1; then
    python_bin=/usr/bin/python3.10
  else
    echo "ROS2 mode requires Python 3.10 with rclpy and backend dependencies." >&2
    echo "Run ./scripts/setup_ros2_backend.sh first." >&2
    exit 1
  fi
else
  python_bin="$project_dir/backend/.venv/bin/python"
  if [[ ! -x "$python_bin" ]]; then
    echo "Backend dependencies are missing. Run ./scripts/setup.sh first." >&2
    exit 1
  fi
fi

echo "Starting backend in ${robot_mode:-mock} mode with $python_bin"
cd "$project_dir/backend"
exec "$python_bin" -m uvicorn main:app --host 0.0.0.0 --port 8000 "${reload_args[@]}"
