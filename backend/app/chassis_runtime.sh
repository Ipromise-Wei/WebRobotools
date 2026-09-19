#!/usr/bin/env bash
set -Eeo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
driver_pid=""
watchdog_pid=""
cleaning=0

cleanup() {
  if [[ "$cleaning" == "1" ]]; then return; fi
  cleaning=1
  trap - EXIT INT TERM
  [[ -n "$watchdog_pid" ]] && kill -TERM "$watchdog_pid" 2>/dev/null || true
  [[ -n "$driver_pid" ]] && kill -TERM "$driver_pid" 2>/dev/null || true
  sleep 1
  [[ -n "$watchdog_pid" ]] && kill -KILL "$watchdog_pid" 2>/dev/null || true
  [[ -n "$driver_pid" ]] && kill -KILL "$driver_pid" 2>/dev/null || true
  wait 2>/dev/null || true
}

trap cleanup EXIT INT TERM

ros2 launch ranger_bringup ranger_mini_v3.launch.py publish_odom_tf:=true &
driver_pid=$!

/usr/bin/python3 "$script_dir/cmd_vel_watchdog.py" \
  --input-topic /webrobot/cmd_vel \
  --output-topic /cmd_vel \
  --status-topic /webrobot/cmd_vel_watchdog/ready \
  --timeout 0.5 &
watchdog_pid=$!

set +e
wait -n "$driver_pid" "$watchdog_pid"
status=$?
set -e
exit "$status"
