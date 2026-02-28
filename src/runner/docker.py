"""Docker sandbox execution for a single agent."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path

import structlog

from src.common.console import C, ok, warn
from src.common.constants import (
    AGENT_MAX_TURNS,
    AGENT_PROMPT,
    AGENT_TIMEOUT_SECS,
    DOCKER_IMAGE,
)
from src.common.logging import get_json_file_logger
from src.runner.agent import Agent


class _TokenTracker:
    """Accumulates token usage from stream-json events and emits periodic logs."""

    def __init__(self, agent_id: str, log_dir: Path) -> None:
        self.agent_id = agent_id
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_creation_tokens = 0
        self.cost_usd = 0.0
        self.num_turns = 0
        self._lock = threading.Lock()
        self._console = structlog.get_logger("token_usage")
        self._file_log = get_json_file_logger(log_dir / "token_usage.jsonl")
        self._start = time.monotonic()

    def update(self, event: dict) -> None:
        """Extract token usage from a stream-json event.

        Usage data can appear in two locations:
        - Top-level ``event["usage"]`` (final result event)
        - Nested ``event["message"]["usage"]`` (intermediate assistant events)
        """
        # Try top-level first (result event), then nested (assistant events)
        usage = event.get("usage") or (event.get("message") or {}).get("usage") or {}
        with self._lock:
            self.input_tokens += usage.get("input_tokens", 0)
            self.output_tokens += usage.get("output_tokens", 0)
            self.cache_read_tokens += usage.get("cache_read_input_tokens", 0)
            self.cache_creation_tokens += usage.get("cache_creation_input_tokens", 0)
            if "cost_usd" in event:
                self.cost_usd = event["cost_usd"]
            if "num_turns" in event:
                self.num_turns = event["num_turns"]

    def snapshot(self) -> dict:
        """Return a copy of current totals."""
        with self._lock:
            return {
                "agent_id": self.agent_id,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "cache_read_tokens": self.cache_read_tokens,
                "cache_creation_tokens": self.cache_creation_tokens,
                "total_tokens": self.input_tokens + self.output_tokens,
                "cost_usd": round(self.cost_usd, 6),
                "num_turns": self.num_turns,
                "elapsed_seconds": round(time.monotonic() - self._start, 1),
            }

    def emit(self) -> None:
        """Log current token totals to console and file."""
        snap = self.snapshot()
        self._console.info("token_usage", **snap)
        self._file_log.info("token_usage", **snap)


def _periodic_emitter(tracker: _TokenTracker, stop: threading.Event) -> None:
    """Background thread: emit token stats every 5 seconds."""
    while not stop.is_set():
        stop.wait(timeout=5.0)
        if not stop.is_set():
            tracker.emit()


def _watchdog(proc: subprocess.Popen, deadline: float, agent_id: str) -> None:
    """Background thread: kill the process if it exceeds the deadline."""
    while proc.poll() is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            proc.kill()
            warn(f"{agent_id} timed out after {AGENT_TIMEOUT_SECS}s — killing container.")
            return
        # Check every 5 seconds
        time.sleep(min(remaining, 5.0))


def run_agent(agent: Agent, log_dir: Path) -> Agent:
    """Launch a Docker sandbox for a single agent and wait for it to finish."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "stdout.log"

    # Mount host's Claude config directory for authentication
    claude_config_dir = Path.home() / ".claude"
    
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{agent.workspace}:/workspace",
        "-v", f"{claude_config_dir}:/home/node/.claude:ro",  # Mount host Claude config (read-only)
        "-w", "/workspace",
        DOCKER_IMAGE,
        "--dangerously-skip-permissions",
        "--max-turns", str(AGENT_MAX_TURNS),
        "--output-format", "stream-json",
        "--verbose",
        "--append-system-prompt-file", agent.intent_file,
        "-p", AGENT_PROMPT,
    ]

    intent_colour = C.MAGENTA if agent.intent == "a" else C.CYAN
    print(f"  {intent_colour}>{C.NC} {agent.agent_id:<12} intent={agent.intent.upper()}  city={agent.city_id[:12]}...")

    tracker = _TokenTracker(agent.agent_id, log_dir)
    stop_emitter = threading.Event()
    emitter_thread = threading.Thread(
        target=_periodic_emitter,
        args=(tracker, stop_emitter),
        name=f"token-emitter-{agent.agent_id}",
        daemon=True,
    )

    try:
        deadline = time.monotonic() + AGENT_TIMEOUT_SECS
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        emitter_thread.start()

        # Watchdog thread enforces the deadline even if stdout blocks
        wd_thread = threading.Thread(
            target=_watchdog,
            args=(proc, deadline, agent.agent_id),
            name=f"watchdog-{agent.agent_id}",
            daemon=True,
        )
        wd_thread.start()

        with open(log_file, "w") as flog:
            for raw_line in proc.stdout:
                line = raw_line.decode("utf-8", errors="replace")
                flog.write(line)

                stripped = line.strip()
                if stripped:
                    try:
                        event = json.loads(stripped)
                        tracker.update(event)
                    except json.JSONDecodeError:
                        pass

        proc.wait(timeout=10)

        if proc.returncode == 0:
            agent.status = "completed"
            ok(f"{agent.agent_id} finished (exit 0).")
        elif proc.returncode == -9:
            agent.status = "failed"
            # Killed by watchdog — message already emitted
        else:
            agent.status = "failed"
            warn(f"{agent.agent_id} finished with exit code {proc.returncode}.")

    except Exception as exc:
        agent.status = "failed"
        warn(f"{agent.agent_id} docker error: {exc}")
    finally:
        stop_emitter.set()
        emitter_thread.join(timeout=10)
        tracker.emit()  # final snapshot

    return agent
