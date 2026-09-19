#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-30}"
python_bin="$project_dir/backend/.venv-ros2/bin/python"
if [[ ! -x "$python_bin" ]]; then echo "Run ./scripts/setup_ros2_backend.sh first." >&2; exit 1; fi
cd "$project_dir/backend"
"$python_bin" -m uvicorn main:app --host 0.0.0.0 --port 8000 &
backend_pid=$!
trap 'kill "$backend_pid" 2>/dev/null || true' EXIT INT TERM
cd "$project_dir"
"$project_dir/scripts/start_frontend.sh"
