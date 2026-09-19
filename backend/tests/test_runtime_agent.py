import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


AGENT = Path(__file__).resolve().parents[1] / "app" / "runtime_agent.py"


def call_agent(state_dir: str, *arguments: str) -> dict[str, object]:
    environment = {**os.environ, "WEBROBOT_STATE_DIR": state_dir}
    result = subprocess.run(
        [sys.executable, str(AGENT), *arguments],
        check=True, capture_output=True, text=True, env=environment, timeout=10,
    )
    return json.loads(result.stdout)


def test_runtime_agent_starts_and_reaps_process_group() -> None:
    manifest = {
        "domain_id": 30,
        "environment_setup": [],
        "tasks": [
            {
                "id": "safe_test_1", "label": "Safe test 1", "command": "sleep 30",
                "startup_delay": 0.1, "ready_command": "", "ready_timeout": 0,
            },
            {
                "id": "safe_test_2", "label": "Safe test 2", "command": "sleep 30",
                "startup_delay": 0.1, "ready_command": "", "ready_timeout": 0,
            },
        ],
    }
    encoded = base64.urlsafe_b64encode(json.dumps(manifest).encode()).decode()
    with tempfile.TemporaryDirectory() as state_dir:
        started = call_agent(state_dir, "start-task", "--task-id", "safe_test_1", "--manifest", encoded)
        assert started["phase"] == "starting"
        try:
            deadline = time.monotonic() + 3
            status = started
            while status["phase"] == "starting" and time.monotonic() < deadline:
                time.sleep(0.1)
                status = call_agent(state_dir, "status")
            assert status["phase"] == "running"
            assert status["tasks"][0]["state"] == "running"  # type: ignore[index]
            second = call_agent(state_dir, "start-task", "--task-id", "safe_test_2", "--manifest", encoded)
            assert second["tasks"][1]["state"] == "starting"  # type: ignore[index]
        finally:
            stopped = call_agent(state_dir, "stop")
        assert stopped["phase"] == "stopped"
        assert stopped["supervisor_pid"] is None
