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
        self._arm_bridge_source = Path(__file__).resolve().parents[1] / "arm_tcp_bridge.py"

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

    async def _deploy_agent(self) -> None:
        remote_dir = str(Path(self.settings.agent_path).parent)
        sources = [
            # Deploy the arm bridge first. Arm state polling starts with the Web
            # service and must never depend on the longer runtime-agent update.
            (self._arm_bridge_source, f"{remote_dir}/arm_tcp_bridge.py"),
            (self._agent_source, self.settings.agent_path),
            (self._watchdog_source, f"{remote_dir}/cmd_vel_watchdog.py"),
            (self._chassis_runtime_source, f"{remote_dir}/chassis_runtime.sh"),
        ]
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

    async def ensure_deployed(self) -> None:
        async with self._lock:
            await self._deploy_agent()

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
            self._merge_configured_tasks(data)
            if int(data.get("agent_version", 0)) < 2 and any(
                task.get("state") in {"starting", "running", "stopping"}
                for task in data["tasks"]
            ):
                data["message"] = "检测到旧版整栈任务，请先全部停止，再使用独立模块开关"
            data.update({"enabled": True, "reachable": True, "host": self.settings.host})
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
            await self._execute(self._agent_command("stop"), timeout=20)
            return await self.status()

    async def logs(self, lines: int = 120) -> list[str]:
        output = await self._execute(self._agent_command("logs", "--lines", str(lines)), timeout=10)
        return output.splitlines()
