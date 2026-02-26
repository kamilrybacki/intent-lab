"""Basic statistical helpers (stdlib only, no numpy needed)."""

from __future__ import annotations

import math


def mean(v: list[float | int]) -> float:
    return sum(v) / len(v) if v else 0.0


def stdev(v: list[float | int]) -> float:
    if len(v) < 2:
        return 0.0
    m = mean(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))


def median(v: list[float | int]) -> float:
    if not v:
        return 0.0
    s = sorted(v)
    n = len(s)
    return float(s[n // 2]) if n % 2 == 1 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def fmt_stat(v: list[float | int]) -> str:
    """Full stats: mean +/- sigma  [min, med, max]  (n=...)."""
    if not v:
        return "—"
    return (
        f"{mean(v):,.1f} ± {stdev(v):,.1f}"
        f"  [min={min(v):,.0f}, med={median(v):,.0f}, max={max(v):,.0f}]"
        f"  (n={len(v)})"
    )
