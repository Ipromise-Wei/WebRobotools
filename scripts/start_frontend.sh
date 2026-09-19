#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -d "$project_dir/frontend/node_modules" ]]; then
  echo "Frontend dependencies are missing. Run ./scripts/setup.sh first." >&2
  exit 1
fi
exec npm --prefix "$project_dir/frontend" run dev

