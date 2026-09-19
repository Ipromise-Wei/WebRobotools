#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="$project_dir/backend/.venv/bin/python"
if [[ ! -x "$python_bin" ]]; then
  echo "Backend dependencies are missing. Run ./scripts/setup.sh first." >&2
  exit 1
fi
cd "$project_dir/backend"
exec "$python_bin" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

