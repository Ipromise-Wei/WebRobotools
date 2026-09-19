#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if /usr/bin/python3.10 -m venv --system-site-packages "$project_dir/backend/.venv-ros2"; then
  "$project_dir/backend/.venv-ros2/bin/pip" install -r "$project_dir/backend/requirements.txt"
else
  echo "python3.10-venv is unavailable; installing backend packages for the local Python 3.10 user."
  /usr/bin/python3.10 -m pip install --user -r "$project_dir/backend/requirements.txt"
fi
