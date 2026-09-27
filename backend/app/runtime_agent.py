#!/usr/bin/env python3
"""Dependency-free per-module ROS2 supervisor deployed to the industrial PC."""

from __future__ import annotations

import argparse
import base64
import fcntl
import json
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


STATE_DIR = Path(os.environ.get("WEBROBOT_STATE_DIR", "~/.local/state/webrobot")).expanduser()
STATE_FILE = STATE_DIR / "runtime.json"
MANIFEST_FILE = STATE_DIR / "manifest.json"
LOG_FILE = STATE_DIR / "runtime.log"
LOCK_FILE = STATE_DIR / "runtime.lock"
ACTIVE_STATES = {"starting", "running", "stopping"}
AGENT_VERSION = 3


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def process_start(pid: int | None) -> int | None:
    if not pid:
        return None
    try:
        content = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        return int(content[content.rfind(")") + 2 :].split()[19])
    except (FileNotFoundError, PermissionError, ValueError, IndexError):
        return None


def alive(pid: int | None, expected_start: int | None = None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return expected_start is None or process_start(pid) == expected_start


def read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


def load_state() -> dict[str, Any]:
    return read_json(STATE_FILE, {"phase": "stopped", "message": "机器人任务未运行", "tasks": []})


def write_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = now()
    fd, temporary = tempfile.mkstemp(prefix="runtime-", suffix=".json", dir=STATE_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False)
        os.replace(temporary, STATE_FILE)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def state_lock() -> Iterator[None]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def task_template(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": config["id"], "label": config["label"], "state": "stopped",
        "pid": None, "pid_start": None, "supervisor_pid": None,
        "supervisor_start": None, "message": "已停止",
        "dependencies": config.get("dependencies", []),
    }


def ensure_tasks(state: dict[str, Any], manifest: dict[str, Any]) -> None:
    current = {task.get("id"): task for task in state.get("tasks", [])}
    state["tasks"] = []
    for config in manifest.get("tasks", []):
        task = {**task_template(config), **current.get(config["id"], {})}
        task["label"] = config["label"]
        task["dependencies"] = config.get("dependencies", [])
        state["tasks"].append(task)


def derive_summary(state: dict[str, Any]) -> None:
    state["agent_version"] = AGENT_VERSION
    state["orchestrating"] = bool(state.get("orchestrator_pid"))
    states = [task.get("state", "stopped") for task in state.get("tasks", [])]
    if state["orchestrating"]:
        state.update(phase="starting", message="正在按依赖顺序启动全部模块")
    elif "error" in states:
        state.update(phase="error", message="部分机器人模块异常")
    elif "starting" in states:
        state.update(phase="starting", message="机器人模块启动中")
    elif "stopping" in states:
        state.update(phase="stopping", message="机器人模块停止中")
    elif "running" in states:
        count = states.count("running")
        state.update(phase="running", message=f"{count} 个机器人模块运行中")
    else:
        state.update(phase="stopped", message="机器人任务未运行")
    state["supervisor_pid"] = None


def normalise_state(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    with state_lock():
        state = load_state()
        if manifest:
            ensure_tasks(state, manifest)
        if state.get("orchestrator_pid") and not alive(
            state.get("orchestrator_pid"), state.get("orchestrator_start")
        ):
            state.update(orchestrator_pid=None, orchestrator_start=None)
        for task in state.get("tasks", []):
            if task.get("state") in ACTIVE_STATES and not alive(task.get("supervisor_pid"), task.get("supervisor_start")):
                if alive(task.get("pid"), task.get("pid_start")):
                    task.update(state="error", message="主管进程退出，模块仍在运行")
                else:
                    task.update(state="error", message="模块意外退出", pid=None, pid_start=None)
                task.update(supervisor_pid=None, supervisor_start=None)
        derive_summary(state)
        write_state(state)
        return state


def update_task(task_id: str, **changes: Any) -> dict[str, Any]:
    with state_lock():
        state = load_state()
        task = next((item for item in state.get("tasks", []) if item.get("id") == task_id), None)
        if task is None:
            raise ValueError(f"未知模块：{task_id}")
        task.update(changes)
        derive_summary(state)
        write_state(state)
        return state


def update_runtime(**changes: Any) -> dict[str, Any]:
    with state_lock():
        state = load_state()
        state.update(changes)
        derive_summary(state)
        write_state(state)
        return state


def shell_command(manifest: dict[str, Any], command: str) -> str:
    setup = [f"source {shlex.quote(path)}" for path in manifest.get("environment_setup", [])]
    setup.append(f"export ROS_DOMAIN_ID={int(manifest.get('domain_id', 30))}")
    setup.append(f"exec {command}")
    return "set -e; " + "; ".join(setup)


def run_hook(manifest: dict[str, Any], command: str, timeout: float, label: str) -> None:
    """Run a configured lifecycle hook; browser input never reaches this path."""
    if not command:
        return
    result = subprocess.run(
        ["bash", "-lc", shell_command(manifest, command)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.stdout:
        print(f"[{now()}] [{label}] {result.stdout.strip()}", flush=True)
    if result.returncode:
        raise RuntimeError(f"{label} failed with exit code {result.returncode}")


def terminate_group(pid: int | None, expected_start: int | None = None, force: bool = False) -> None:
    if not alive(pid, expected_start):
        return
    try:
        os.killpg(pid, signal.SIGKILL if force else signal.SIGTERM)
    except ProcessLookupError:
        pass


def supervise_task(manifest: dict[str, Any], task_id: str) -> int:
    config = next((task for task in manifest.get("tasks", []) if task["id"] == task_id), None)
    if config is None:
        raise ValueError(f"未知模块：{task_id}")
    stop_requested = False
    process: subprocess.Popen[Any] | None = None
    process_started: int | None = None

    def request_stop(_signum: int, _frame: Any) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    update_task(
        task_id, state="starting", message="正在启动",
        supervisor_pid=os.getpid(), supervisor_start=process_start(os.getpid()),
    )
    failed_message = ""
    try:
        print(f"[{now()}] [{config['label']}] starting", flush=True)
        process = subprocess.Popen(
            ["bash", "-lc", shell_command(manifest, config["command"])],
            start_new_session=True,
        )
        process_started = process_start(process.pid)
        update_task(task_id, pid=process.pid, pid_start=process_started)

        deadline = time.monotonic() + float(config.get("startup_delay", 0))
        while time.monotonic() < deadline and not stop_requested:
            if process.poll() is not None:
                raise RuntimeError(f"启动失败，退出码 {process.returncode}")
            time.sleep(0.2)

        ready_command = config.get("ready_command", "")
        ready_timeout = float(config.get("ready_timeout", 0))
        if ready_command and ready_timeout and not stop_requested:
            update_task(task_id, message="等待数据就绪")
            ready_deadline = time.monotonic() + ready_timeout
            while not stop_requested:
                if process.poll() is not None:
                    raise RuntimeError(f"就绪前退出，退出码 {process.returncode}")
                check = subprocess.run(
                    ["bash", "-lc", shell_command(manifest, ready_command)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=5, check=False,
                )
                if check.returncode == 0:
                    break
                if time.monotonic() >= ready_deadline:
                    raise RuntimeError("等待数据就绪超时")
                time.sleep(1)

        if not stop_requested:
            run_hook(
                manifest, str(config.get("on_start_command", "")), 25,
                f"{config['label']} start hook",
            )
            update_task(task_id, state="running", message="运行中")
            print(f"[{now()}] [{config['label']}] running", flush=True)
        while process.poll() is None and not stop_requested:
            time.sleep(0.5)
        if not stop_requested:
            raise RuntimeError(f"意外退出，退出码 {process.returncode}")
    except Exception as exc:
        failed_message = str(exc)
    finally:
        if process is not None:
            if alive(process.pid, process_started):
                try:
                    run_hook(
                        manifest, str(config.get("on_stop_command", "")), 15,
                        f"{config['label']} stop hook",
                    )
                except (RuntimeError, subprocess.TimeoutExpired) as exc:
                    print(f"[{now()}] [{config['label']}] stop hook warning: {exc}", flush=True)
            terminate_group(process.pid, process_started)
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                terminate_group(process.pid, process_started, force=True)
        if failed_message:
            update_task(
                task_id, state="error", message=failed_message, pid=None, pid_start=None,
                supervisor_pid=None, supervisor_start=None,
            )
            print(f"[{now()}] [{config['label']}] error: {failed_message}", flush=True)
            return 1
        update_task(
            task_id, state="stopped", message="已停止", pid=None, pid_start=None,
            supervisor_pid=None, supervisor_start=None,
        )
        print(f"[{now()}] [{config['label']}] stopped", flush=True)
    return 0


def decode_manifest(encoded: str) -> dict[str, Any]:
    manifest = json.loads(base64.urlsafe_b64decode(encoded.encode()).decode())
    if not manifest.get("tasks"):
        raise ValueError("任务清单为空")
    for task in manifest["tasks"]:
        if not all(isinstance(task.get(key), str) and task[key] for key in ("id", "label", "command")):
            raise ValueError("任务定义无效")
    task_ids = {task["id"] for task in manifest["tasks"]}
    for profile in manifest.get("profiles", []):
        if not isinstance(profile.get("id"), str) or not profile["id"]:
            raise ValueError("运行方案定义无效")
        if not isinstance(profile.get("tasks"), list) or not profile["tasks"]:
            raise ValueError("运行方案任务为空")
        if any(task_id not in task_ids for task_id in profile["tasks"]):
            raise ValueError("运行方案包含未知任务")
    return manifest


def save_manifest(manifest: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_FILE.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


def start_task(task_id: str, manifest: dict[str, Any]) -> dict[str, Any]:
    save_manifest(manifest)
    state = normalise_state(manifest)
    task = next((item for item in state["tasks"] if item["id"] == task_id), None)
    if task is None:
        raise ValueError(f"未知模块：{task_id}")
    if task["state"] in ACTIVE_STATES:
        return state
    missing = [
        dependency for dependency in task.get("dependencies", [])
        if next((item for item in state["tasks"] if item["id"] == dependency and item["state"] == "running"), None) is None
    ]
    if missing:
        labels = [next((item["label"] for item in state["tasks"] if item["id"] == item_id), item_id) for item_id in missing]
        raise ValueError("请先开启依赖模块：" + "、".join(labels))
    if alive(task.get("pid"), task.get("pid_start")):
        raise RuntimeError("检测到残留进程，请先关闭该模块")

    log = LOG_FILE.open("a", encoding="utf-8")
    supervisor = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "supervise-task", "--task-id", task_id, "--manifest-file", str(MANIFEST_FILE)],
        start_new_session=True, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
    )
    log.close()
    return update_task(
        task_id, state="starting", message="正在创建模块进程",
        supervisor_pid=supervisor.pid, supervisor_start=process_start(supervisor.pid),
    )


def orchestrate_start(manifest: dict[str, Any], task_ids: list[str]) -> int:
    cancelled = False

    def request_stop(_signum: int, _frame: Any) -> None:
        nonlocal cancelled
        cancelled = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    update_runtime(
        orchestrator_pid=os.getpid(),
        orchestrator_start=process_start(os.getpid()),
    )
    pending = list(task_ids)
    try:
        print(f"[{now()}] [all] dependency-ordered startup requested", flush=True)
        while pending and not cancelled:
            progressed = False
            for task_id in list(pending):
                if cancelled:
                    break
                state = normalise_state(manifest)
                task = next(item for item in state["tasks"] if item["id"] == task_id)
                if task["state"] == "running":
                    pending.remove(task_id)
                    progressed = True
                    continue
                dependencies_ready = all(
                    next(
                        (item["state"] for item in state["tasks"] if item["id"] == dependency),
                        "stopped",
                    ) == "running"
                    for dependency in task.get("dependencies", [])
                )
                if not dependencies_ready:
                    continue

                config = next(item for item in manifest["tasks"] if item["id"] == task_id)
                start_task(task_id, manifest)
                timeout = (
                    float(config.get("startup_delay", 0))
                    + float(config.get("ready_timeout", 0))
                    + 20
                )
                deadline = time.monotonic() + max(timeout, 20)
                while not cancelled:
                    state = normalise_state(manifest)
                    task = next(item for item in state["tasks"] if item["id"] == task_id)
                    if task["state"] == "running":
                        pending.remove(task_id)
                        progressed = True
                        break
                    if task["state"] == "error":
                        raise RuntimeError(f"{task['label']}：{task['message']}")
                    if time.monotonic() >= deadline:
                        raise RuntimeError(f"{task['label']}：等待启动完成超时")
                    time.sleep(0.5)
            if pending and not progressed and not cancelled:
                labels = []
                state = normalise_state(manifest)
                for task_id in pending:
                    task = next(item for item in state["tasks"] if item["id"] == task_id)
                    labels.append(task["label"])
                raise RuntimeError("模块依赖无法满足：" + "、".join(labels))
        if cancelled:
            print(f"[{now()}] [all] startup cancelled", flush=True)
        else:
            print(f"[{now()}] [all] all modules are running", flush=True)
        return 0
    except Exception as exc:
        print(f"[{now()}] [all] startup failed: {exc}", flush=True)
        return 1
    finally:
        update_runtime(orchestrator_pid=None, orchestrator_start=None)


def start_all(manifest: dict[str, Any]) -> dict[str, Any]:
    save_manifest(manifest)
    state = normalise_state(manifest)
    if alive(state.get("orchestrator_pid"), state.get("orchestrator_start")):
        return state
    task_ids = [task["id"] for task in manifest.get("tasks", []) if task.get("include_in_start_all", True)]
    if not task_ids:
        raise ValueError("没有配置默认启动任务")
    if all(
        next((item.get("state") for item in state.get("tasks", []) if item.get("id") == task_id), "stopped") == "running"
        for task_id in task_ids
    ):
        return state
    return start_profile(manifest, "__default__", task_ids)


def start_profile(manifest: dict[str, Any], profile_id: str, task_ids: list[str] | None = None) -> dict[str, Any]:
    if task_ids is None:
        profile = next((item for item in manifest.get("profiles", []) if item.get("id") == profile_id), None)
        if profile is None:
            raise ValueError(f"未知运行方案：{profile_id}")
        task_ids = list(profile["tasks"])
    save_manifest(manifest)
    state = normalise_state(manifest)
    if alive(state.get("orchestrator_pid"), state.get("orchestrator_start")):
        return state
    log = LOG_FILE.open("a", encoding="utf-8")
    orchestrator = subprocess.Popen(
        [
            sys.executable, str(Path(__file__).resolve()), "orchestrate",
            "--manifest-file", str(MANIFEST_FILE), "--task-ids",
            ",".join(task_ids),
        ],
        start_new_session=True, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
    )
    log.close()
    return update_runtime(
        orchestrator_pid=orchestrator.pid,
        orchestrator_start=process_start(orchestrator.pid),
    )


def stop_task(task_id: str, enforce_dependents: bool = True) -> dict[str, Any]:
    state = normalise_state()
    task = next((item for item in state.get("tasks", []) if item.get("id") == task_id), None)
    if task is None:
        raise ValueError(f"未知模块：{task_id}")
    if enforce_dependents:
        dependents = [
            item["label"] for item in state.get("tasks", [])
            if task_id in item.get("dependencies", []) and (
                item.get("state") in ACTIVE_STATES
                or alive(item.get("pid"), item.get("pid_start"))
            )
        ]
        if dependents:
            raise ValueError("请先关闭依赖此模块的任务：" + "、".join(dependents))

    supervisor = task.get("supervisor_pid")
    supervisor_start = task.get("supervisor_start")
    if alive(supervisor, supervisor_start):
        os.kill(supervisor, signal.SIGTERM)
        deadline = time.monotonic() + 12
        while alive(supervisor, supervisor_start) and time.monotonic() < deadline:
            time.sleep(0.2)
        if alive(supervisor, supervisor_start):
            os.kill(supervisor, signal.SIGKILL)
    terminate_group(task.get("pid"), task.get("pid_start"))
    time.sleep(0.2)
    terminate_group(task.get("pid"), task.get("pid_start"), force=True)
    return update_task(
        task_id, state="stopped", message="已停止", pid=None, pid_start=None,
        supervisor_pid=None, supervisor_start=None,
    )


def stop_all() -> dict[str, Any]:
    state = normalise_state()
    orchestrator = state.get("orchestrator_pid")
    orchestrator_start = state.get("orchestrator_start")
    if alive(orchestrator, orchestrator_start) and orchestrator != os.getpid():
        os.kill(orchestrator, signal.SIGTERM)
        deadline = time.monotonic() + 4
        while alive(orchestrator, orchestrator_start) and time.monotonic() < deadline:
            time.sleep(0.1)
        if alive(orchestrator, orchestrator_start):
            os.kill(orchestrator, signal.SIGKILL)
        update_runtime(orchestrator_pid=None, orchestrator_start=None)
        state = normalise_state()
    for task in reversed(state.get("tasks", [])):
        stop_task(task["id"], enforce_dependents=False)
    return normalise_state()


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("start-task", "restart-task"):
        command = commands.add_parser(action)
        command.add_argument("--task-id", required=True)
        command.add_argument("--manifest", required=True)
    stop_parser = commands.add_parser("stop-task")
    stop_parser.add_argument("--task-id", required=True)
    supervisor = commands.add_parser("supervise-task")
    supervisor.add_argument("--task-id", required=True)
    supervisor.add_argument("--manifest-file", required=True)
    start_all_parser = commands.add_parser("start-all")
    start_all_parser.add_argument("--manifest", required=True)
    start_profile_parser = commands.add_parser("start-profile")
    start_profile_parser.add_argument("--profile", required=True)
    start_profile_parser.add_argument("--manifest", required=True)
    orchestrator = commands.add_parser("orchestrate")
    orchestrator.add_argument("--manifest-file", required=True)
    orchestrator.add_argument("--task-ids", required=True)
    commands.add_parser("stop")
    commands.add_parser("status")
    log_parser = commands.add_parser("logs")
    log_parser.add_argument("--lines", type=int, default=120)
    args = parser.parse_args()

    if args.action == "supervise-task":
        manifest = read_json(Path(args.manifest_file), {})
        return supervise_task(manifest, args.task_id)
    if args.action == "orchestrate":
        manifest = read_json(Path(args.manifest_file), {})
        return orchestrate_start(manifest, [item for item in args.task_ids.split(",") if item])
    if args.action == "logs":
        try:
            lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        except FileNotFoundError:
            lines = []
        print("\n".join(lines[-max(1, min(args.lines, 500)) :]))
        return 0
    if args.action == "status":
        result = normalise_state()
    elif args.action == "stop":
        result = stop_all()
    elif args.action == "start-all":
        result = start_all(decode_manifest(args.manifest))
    elif args.action == "start-profile":
        result = start_profile(decode_manifest(args.manifest), args.profile)
    elif args.action == "stop-task":
        result = stop_task(args.task_id)
    else:
        manifest = decode_manifest(args.manifest)
        if args.action == "restart-task":
            try:
                stop_task(args.task_id)
            except ValueError as exc:
                if "未知模块" not in str(exc):
                    raise
        result = start_task(args.task_id, manifest)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from None
