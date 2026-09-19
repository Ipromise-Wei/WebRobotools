#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 -m venv "$project_dir/backend/.venv"
"$project_dir/backend/.venv/bin/pip" install -r "$project_dir/backend/requirements-dev.txt"
npm --prefix "$project_dir/frontend" install

