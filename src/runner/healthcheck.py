"""Periodic health-check poller for running agent cities."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import structlog

from src.common.constants import HS_API
from src.common.http import http_get
from src.common.logging import get_json_file_logger


class HealthChecker:
    """Context manager that polls city stats on a background daemon thread.

    Usage::

        targets = [("a-01", city_a_id), ("b-01", city_b_id)]
        with HealthChecker(targets, hs_key, log_dir=results_dir, interval=30):
            # ... run agents ...
    """

    def __init__(
        self,
        targets: list[tuple[str, str]],
        hs_key: str,
        *,
        log_dir: Path,
        interval: float = 30.0,
    ) -> None:
        self._targets = targets
        self._hs_key = hs_key
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._start_time: float = 0.0

        self._console = structlog.get_logger("healthcheck")
        self._file_log = get_json_file_logger(log_dir / "healthcheck.jsonl")

    def __enter__(self) -> HealthChecker:
        self._start_time = time.monotonic()
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="healthcheck-poller",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval + 5)

    def _poll_loop(self) -> None:
        """Poll all targets, then sleep until the next interval."""
        while not self._stop.is_set():
            elapsed = time.monotonic() - self._start_time
            for agent_id, city_id in self._targets:
                self._poll_one(agent_id, city_id, elapsed)
            self._stop.wait(timeout=self._interval)

    def _poll_one(self, agent_id: str, city_id: str, elapsed: float) -> None:
        """Fetch city stats for one agent and emit structured log events."""
        url = f"{HS_API}/v1/cities/{city_id}"
        headers = {"Authorization": f"Bearer {self._hs_key}"}
        try:
            data = http_get(url, headers=headers, timeout=10)
        except Exception as exc:
            self._console.warning(
                "healthcheck_poll_failed",
                agent_id=agent_id,
                city_id=city_id,
                error=str(exc),
            )
            self._file_log.warning(
                "healthcheck_poll_failed",
                agent_id=agent_id,
                city_id=city_id,
                error=str(exc),
            )
            return

        event = {
            "agent_id": agent_id,
            "city_id": city_id,
            "population": data.get("population"),
            "score": data.get("score"),
            "funds": data.get("funds"),
            "game_year": data.get("game_year"),
            "elapsed_seconds": round(elapsed, 1),
        }

        self._console.info("healthcheck", **event)
        self._file_log.info("healthcheck", **event)
