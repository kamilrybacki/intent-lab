"""Docker sandbox execution for a single agent."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from src.common.console import C, ok, warn
from src.common.constants import (
    AGENT_MAX_TURNS,
    AGENT_PROMPT,
    AGENT_TIMEOUT_SECS,
    CCR_HOST,
    CCR_PORT,
    DOCKER_IMAGE,
)
from src.runner.agent import Agent


def _write_env_file(ccr_api_key: str) -> str:
    """Write Docker env vars to a temp file (avoids leaking secrets via ps)."""
    fd, path = tempfile.mkstemp(prefix="intent-env-", suffix=".env")
    with os.fdopen(fd, "w") as f:
        f.write(f"ANTHROPIC_BASE_URL=http://{CCR_HOST}:{CCR_PORT}\n")
        f.write(f"ANTHROPIC_AUTH_TOKEN={ccr_api_key}\n")
        f.write(f"NO_PROXY=127.0.0.1,{CCR_HOST}\n")
    os.chmod(path, 0o600)
    return path


def run_agent(agent: Agent, ccr_api_key: str, log_dir: Path) -> Agent:
    """Launch a Docker sandbox for a single agent and wait for it to finish."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "stdout.log"

    env_file = _write_env_file(ccr_api_key)

    cmd = [
        "docker", "run", "--rm",
        "--env-file", env_file,
        "-v", f"{agent.workspace}:/workspace",
        "-w", "/workspace",
        "--add-host", f"{CCR_HOST}:host-gateway",
        DOCKER_IMAGE,
        "--dangerously-skip-permissions",
        "--max-turns", str(AGENT_MAX_TURNS),
        "--append-system-prompt-file", agent.intent_file,
        "-p", AGENT_PROMPT,
    ]

    intent_colour = C.MAGENTA if agent.intent == "a" else C.CYAN
    print(f"  {intent_colour}>{C.NC} {agent.agent_id:<12} intent={agent.intent.upper()}  city={agent.city_id[:12]}...")

    try:
        with open(log_file, "w") as flog:
            result = subprocess.run(
                cmd, stdout=flog, stderr=subprocess.STDOUT,
                timeout=AGENT_TIMEOUT_SECS,
            )
        if result.returncode == 0:
            agent.status = "completed"
            ok(f"{agent.agent_id} finished (exit 0).")
        else:
            agent.status = "failed"
            warn(f"{agent.agent_id} finished with exit code {result.returncode}.")
    except subprocess.TimeoutExpired:
        agent.status = "failed"
        warn(f"{agent.agent_id} timed out after {AGENT_TIMEOUT_SECS}s — killing container.")
    except Exception as exc:
        agent.status = "failed"
        warn(f"{agent.agent_id} docker error: {exc}")
    finally:
        os.unlink(env_file)

    return agent
