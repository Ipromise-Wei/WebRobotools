#!/usr/bin/env bash
set -Eeo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
driver_pid=""
watchdog_pid=""
can_monitor_pid=""
cleaning=0

# CAN0 is provisioned outside WebRobotTools. Never bring it up/down or change
# its bitrate here; reject chassis startup and stop the managed processes if
# the externally managed link becomes unavailable.
check_can0() {
  local link detail flags
  if ! link="$(/usr/sbin/ip -o link show dev can0 2>/dev/null)"; then
    echo "工控机未找到 can0，或当前用户无法读取其状态" >&2
    return 1
  fi
  flags="${link#*<}"
  flags="${flags%%>*}"
  if [[ ",$flags," != *",UP,"* ]]; then
    echo "can0 未启用；请在工控机上配置后再启动底盘" >&2
    return 1
  fi
  if ! detail="$(/usr/sbin/ip -details link show dev can0 2>/dev/null)"; then
    echo "无法读取 can0 比特率" >&2
    return 1
  fi
  if [[ ! "$detail" =~ (^|[[:space:]])bitrate[[:space:]]+500000([[:space:]]|$) ]]; then
    echo "can0 比特率不是 500000 bit/s" >&2
    return 1
  fi
  if [[ "$detail" =~ (^|[[:space:]])state[[:space:]]+BUS-OFF([[:space:]]|$) ]]; then
    echo "can0 处于 BUS-OFF，底盘已停止" >&2
    return 1
  fi
}

monitor_can0() {
  while true; do
    check_can0 || return 1
    sleep 1
  done
}

cleanup() {
  if [[ "$cleaning" == "1" ]]; then return; fi
  cleaning=1
  trap - EXIT INT TERM
  [[ -n "$can_monitor_pid" ]] && kill -TERM "$can_monitor_pid" 2>/dev/null || true
  [[ -n "$watchdog_pid" ]] && kill -TERM "$watchdog_pid" 2>/dev/null || true
  [[ -n "$driver_pid" ]] && kill -TERM "$driver_pid" 2>/dev/null || true
  sleep 1
  [[ -n "$can_monitor_pid" ]] && kill -KILL "$can_monitor_pid" 2>/dev/null || true
  [[ -n "$watchdog_pid" ]] && kill -KILL "$watchdog_pid" 2>/dev/null || true
  [[ -n "$driver_pid" ]] && kill -KILL "$driver_pid" 2>/dev/null || true
  wait 2>/dev/null || true
}

trap cleanup EXIT INT TERM

check_can0
monitor_can0 &
can_monitor_pid=$!

ros2 launch ranger_bringup ranger_mini_v3.launch.py publish_odom_tf:=true &
driver_pid=$!

/usr/bin/python3 "$script_dir/cmd_vel_watchdog.py" \
  --input-topic /webrobot/cmd_vel \
  --output-topic /cmd_vel \
  --navigation-topic /webrobot/nav_cmd_vel \
  --navigation-active-topic /webrobot/navigation/active \
  --status-topic /webrobot/cmd_vel_watchdog/ready \
  --timeout 0.5 &
watchdog_pid=$!

set +e
wait -n "$driver_pid" "$watchdog_pid" "$can_monitor_pid"
status=$?
set -e
exit "$status"
