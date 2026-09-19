#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for port in 8000 5173; do
  if ss -ltnH "sport = :$port" | grep -q .; then
    echo "Port $port is already in use. Stop the existing WebRobotTools process before starting another instance." >&2
    echo "Inspect it with: ss -ltnp 'sport = :$port'" >&2
    exit 1
  fi
done

"$project_dir/scripts/start_backend.sh" &
backend_pid=$!
trap 'kill "$backend_pid" 2>/dev/null || true' EXIT INT TERM

backend_ready=0
for _ in {1..40}; do
  if ! kill -0 "$backend_pid" 2>/dev/null; then
    wait "$backend_pid" || true
    echo "Backend failed to start; frontend was not started." >&2
    exit 1
  fi
  if curl --silent --fail http://127.0.0.1:8000/health >/dev/null 2>&1; then
    backend_ready=1
    break
  fi
  sleep 0.25
done

if [[ "$backend_ready" != "1" ]]; then
  echo "Backend health check timed out." >&2
  exit 1
fi

"$project_dir/scripts/start_frontend.sh"
