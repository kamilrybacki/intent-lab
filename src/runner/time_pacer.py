"""Centralized simulation-time pacer for agent cities.

Advances time for all cities at a fixed real-world interval, ensuring
every agent experiences the same game-time progression regardless of
how fast or slow it builds.
"""

from __future__ import annotations

import json
import threading
import time

import structlog

from src.common.constants import HS_API
from src.common.http import http_post


class TimePacer:
    """Context manager that advances simulation time on a fixed schedule.

    Each tick calls ``POST /v1/cities/:id/advance`` with ``months=1``
    for every tracked city.

    Usage::

        targets = [("a-01", city_a_id), ("b-01", city_b_id)]
        with TimePacer(targets, hs_key, total_cycles=150, interval=18.0):
            # ... run agents ...
    """

    def __init__(
        self,
        targets: list[tuple[str, str]],
        hs_key: str,
        *,
        total_cycles: int = 150,
        interval: float = 18.0,
    ) -> None:
        self._targets = targets
        self._hs_key = hs_key
        self._total_cycles = total_cycles
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._cycle = 0
        self._log = structlog.get_logger("time_pacer")

    @property
    def cycle(self) -> int:
        return self._cycle

    def __enter__(self) -> TimePacer:
        self._thread = threading.Thread(
            target=self._pace_loop,
            name="time-pacer",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval + 5)

    def _pace_loop(self) -> None:
        """Advance all cities by 1 month on each tick."""
        while not self._stop.is_set() and self._cycle < self._total_cycles:
            self._stop.wait(timeout=self._interval)
            if self._stop.is_set():
                break

            self._cycle += 1
            for agent_id, city_id in self._targets:
                self._advance_one(agent_id, city_id)

            self._log.info(
                "time_tick",
                cycle=self._cycle,
                total=self._total_cycles,
                remaining=self._total_cycles - self._cycle,
            )

        if self._cycle >= self._total_cycles:
            self._log.info("time_pacer_done", total_cycles=self._total_cycles)

    def _advance_one(self, agent_id: str, city_id: str) -> None:
        """POST advance for a single city."""
        url = f"{HS_API}/v1/cities/{city_id}/advance"
        headers = {
            "Authorization": f"Bearer {self._hs_key}",
            "Content-Type": "application/json",
        }
        body = json.dumps({"months": 1}).encode()
        try:
            http_post(url, headers=headers, body=body, timeout=10)
        except Exception as exc:
            self._log.warning(
                "time_advance_failed",
                agent_id=agent_id,
                city_id=city_id,
                cycle=self._cycle,
                error=str(exc),
            )
