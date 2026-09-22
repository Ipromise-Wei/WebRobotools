import asyncio
import base64
import json
import shlex
from pathlib import Path
from typing import Any

from app.core.config import RemoteRuntimeSettings
from app.models.runtime import RuntimeStatus


class RemoteRuntimeError(RuntimeError):
    pass


class RemoteRuntimeManager:
    """Controls one allow-listed robot runtime over an SSH transport."""

    def __init__(self, settings: RemoteRuntimeSettings) -> None:
        self.settings = settings
        self._lock = asyncio.Lock()
        self._agent_source = Path(__file__).resolve().parents[1] / "runtime_agent.py"
        self._watchdog_source = Path(__file__).resolve().parents[1] / "cmd_vel_watchdog.py"
        self._chassis_runtime_source = Path(__file__).resolve().parents[1] / "chassis_runtime.sh"
        self._nav2_source = Path(__file__).resolve().parents[1] / "nav2_web_runtime.py"
        self._arm_bridge_source = Path(__file__).resolve().parents[1] / "arm_tcp_bridge.py"
        self._arm_bridge_deployed = False

    @property
    def target(self) -> str:
        return f"{self.settings.user}@{self.settings.host}"

    def _ssh_options(self, port_flag: str = "-p") -> list[str]:
        return [
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"ConnectTimeout={int(self.settings.connect_timeout)}",
            port_flag, str(self.settings.port),
        ]

    async def _execute(self, command: str, timeout: float = 15) -> str:
        if not self.settings.enabled:
            raise RemoteRuntimeError("remote runtime control is disabled")
        process = await asyncio.create_subprocess_exec(
            "ssh", *self._ssh_options(), self.target, command,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise RemoteRuntimeError("industrial PC command timed out") from None
        if process.returncode:
            detail = stderr.decode(errors="replace").strip() or stdout.decode(errors="replace").strip()
            raise RemoteRuntimeError(detail or f"SSH exited with status {process.returncode}")
        return stdout.decode(errors="replace").strip()

    async def _deploy_sources(self, sources: list[tuple[Path, str]]) -> None:
        remote_dir = str(Path(self.settings.agent_path).parent)
        if any(not source.is_file() for source, _ in sources):
            raise RemoteRuntimeError("runtime support files are missing")
        await self._execute(f"mkdir -p {shlex.quote(remote_dir)}")
        for source, destination in sources:
            process = await asyncio.create_subprocess_exec(
                "scp", *self._ssh_options("-P"), str(source),
                f"{self.target}:{destination}",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=15
                )
            except TimeoutError:
                process.kill()
                await process.wait()
                raise RemoteRuntimeError(
                    f"deploying {source.name} to the industrial PC timed out"
                ) from None
            if process.returncode:
                detail = stderr.decode(errors="replace").strip() or stdout.decode(errors="replace").strip()
                raise RemoteRuntimeError(detail or f"failed to deploy {source.name}")
        paths = " ".join(shlex.quote(destination) for _, destination in sources)
        await self._execute(f"chmod 700 {paths}")

    async def _deploy_agent(self) -> None:
        remote_dir = str(Path(self.settings.agent_path).parent)
        await self._deploy_sources([
            # Deploy the arm bridge first so an operator can connect the arm
            # without depending on the runtime agent's first command.
            (self._arm_bridge_source, f"{remote_dir}/arm_tcp_bridge.py"),
            (self._agent_source, self.settings.agent_path),
            (self._watchdog_source, f"{remote_dir}/cmd_vel_watchdog.py"),
            (self._nav2_source, f"{remote_dir}/nav2_web_runtime.py"),
            (self._chassis_runtime_source, f"{remote_dir}/chassis_runtime.sh"),
        ])
        self._arm_bridge_deployed = True

    async def ensure_deployed(self) -> None:
        async with self._lock:
            await self._deploy_agent()

    async def ensure_arm_bridge_deployed(self) -> None:
        """Deploy the fixed arm bridge on demand before opening the link."""
        async with self._lock:
            if self._arm_bridge_deployed:
                return
            remote_dir = str(Path(self.settings.agent_path).parent)
            await self._deploy_sources([
                (self._arm_bridge_source, f"{remote_dir}/arm_tcp_bridge.py"),
            ])
            self._arm_bridge_deployed = True

    def _manifest(self) -> str:
        payload = {
            "domain_id": self.settings.domain_id,
            "environment_setup": self.settings.environment_setup,
            "tasks": [task.model_dump() for task in self.settings.tasks],
        }
        return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()

    def _agent_command(self, action: str, *arguments: str) -> str:
        parts = ["/usr/bin/python3", self.settings.agent_path, action, *arguments]
        return " ".join(shlex.quote(part) for part in parts)

    def _fallback(self, phase: str, message: str, reachable: bool = False) -> RuntimeStatus:
        return RuntimeStatus(
            enabled=self.settings.enabled, reachable=reachable, phase=phase,
            host=self.settings.host, message=message,
            tasks=self._configured_tasks() if self.settings.enabled else [],
        )

    def _configured_tasks(self) -> list[dict[str, Any]]:
        return [
            {
                "id": task.id, "label": task.label, "state": "stopped",
                "pid": None, "message": "已停止", "dependencies": task.dependencies,
            }
            for task in self.settings.tasks
        ]

    def _merge_configured_tasks(self, data: dict[str, Any]) -> None:
        current = {task.get("id"): task for task in data.get("tasks", [])}
        data["tasks"] = [
            {**configured, **current.get(configured["id"], {})}
            for configured in self._configured_tasks()
        ]

    async def status(self) -> RuntimeStatus:
        if not self.settings.enabled:
            return self._fallback("disabled", "远程运行控制未启用")
        try:
            output = await self._execute(self._agent_command("status"), timeout=8)
        except RemoteRuntimeError as exc:
            message = str(exc)
            if "No such file" in message or "can't open file" in message:
                return self._fallback("unconfigured", "运行代理尚未部署", True)
            return self._fallback("offline", message)
        try:
            data: dict[str, Any] = json.loads(output)
            legacy_can0 = next((task for task in data.get("tasks", []) if task.get("id") == "can0"), None)
            legacy_can0_active = bool(legacy_can0 and (
                legacy_can0.get("state") in {"starting", "running", "stopping"}
                or legacy_can0.get("pid") is not None
                or legacy_can0.get("supervisor_pid") is not None
            ))
            self._merge_configured_tasks(data)
            if (
                legacy_can0
                and not legacy_can0_active
                and legacy_can0.get("state") == "error"
                and data.get("phase") == "error"
                and not data.get("orchestrating")
                and not any(task.get("state") == "error" for task in data["tasks"])
            ):
                states = [task.get("state") for task in data["tasks"]]
                if "starting" in states:
                    data.update(phase="starting", message="机器人模块启动中")
                elif "stopping" in states:
                    data.update(phase="stopping", message="机器人模块停止中")
                elif "running" in states:
                    data.update(phase="running", message=f"{states.count('running')} 个机器人模块运行中")
                else:
                    data.update(phase="stopped", message="机器人任务未运行")
            if legacy_can0_active:
                data["phase"] = "error"
                data["message"] = "旧版 Web CAN0 管理任务仍在运行。请先按现场流程退出旧任务并确认 CAN0 已恢复；当前版本不会自动停止或重配网卡。"
            elif int(data.get("agent_version", 0)) < 2 and any(
                task.get("state") in {"starting", "running", "stopping"}
                for task in data["tasks"]
            ):
                data["message"] = "检测到旧版整栈任务，请先全部停止，再使用独立模块开关"
            data.update({"enabled": True, "reachable": True, "host": self.settings.host, "legacy_can0_active": legacy_can0_active})
            return RuntimeStatus.model_validate(data)
        except (json.JSONDecodeError, ValueError) as exc:
            return self._fallback("error", f"无效的运行代理响应：{exc}", True)

    def _validate_task(self, task_id: str) -> None:
        if task_id not in {task.id for task in self.settings.tasks}:
            raise RemoteRuntimeError(f"unknown runtime task: {task_id}")

    async def task_action(self, task_id: str, action: str) -> RuntimeStatus:
        self._validate_task(task_id)
        if action not in {"start", "stop", "restart"}:
            raise RemoteRuntimeError(f"unsupported task action: {action}")
        async with self._lock:
            current = await self.status()
            if action in {"start", "restart"} and current.legacy_can0_active:
                raise RemoteRuntimeError(current.message)
            if current.agent_version < 2 and any(
                task.state in {"starting", "running", "stopping"} for task in current.tasks
            ):
                raise RemoteRuntimeError("检测到旧版整栈任务，请先点击“全部停止”，再操作独立模块")
            await self._deploy_agent()
            command = f"{action}-task"
            arguments = ["--task-id", task_id]
            if action in {"start", "restart"}:
                arguments += ["--manifest", self._manifest()]
            await self._execute(self._agent_command(command, *arguments), timeout=25)
            return await self.status()

    async def start(self) -> RuntimeStatus:
        async with self._lock:
            current = await self.status()
            if current.legacy_can0_active:
                raise RemoteRuntimeError(current.message)
            if current.agent_version < 2 and any(
                task.state in {"starting", "running", "stopping"} for task in current.tasks
            ):
                raise RemoteRuntimeError("检测到旧版整栈任务，请先点击“全部停止”，再执行一键全启")
            await self._deploy_agent()
            await self._execute(
                self._agent_command("start-all", "--manifest", self._manifest()),
                timeout=25,
            )
            return await self.status()

    async def stop(self) -> RuntimeStatus:
        async with self._lock:
            current = await self.status()
            if current.legacy_can0_active:
                raise RemoteRuntimeError("旧版 Web CAN0 管理任务仍在运行；一键全停会将 CAN0 拉低，请先按现场流程退出旧任务")
            await self._execute(self._agent_command("stop"), timeout=20)
            return await self.status()

    async def logs(self, lines: int = 120) -> list[str]:
        output = await self._execute(self._agent_command("logs", "--lines", str(lines)), timeout=10)
        return output.splitlines()
