#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! /usr/bin/python3.10 -m venv --system-site-packages "$project_dir/backend/.venv-ros2"; then
  echo "Please install: sudo apt install python3.10-venv" >&2; exit 1
fi
"$project_dir/backend/.venv-ros2/bin/pip" install -r "$project_dir/backend/requirements.txt"
