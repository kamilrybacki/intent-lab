"""ANSI colour codes and logging helpers."""

from __future__ import annotations

import sys


class C:
    """ANSI colour codes (no-op if not a tty)."""

    _tty = sys.stdout.isatty()
    RED = "\033[0;31m" if _tty else ""
    GREEN = "\033[0;32m" if _tty else ""
    CYAN = "\033[0;36m" if _tty else ""
    YELLOW = "\033[1;33m" if _tty else ""
    MAGENTA = "\033[0;35m" if _tty else ""
    BOLD = "\033[1m" if _tty else ""
    NC = "\033[0m" if _tty else ""


def info(msg: str) -> None:
    print(f"{C.CYAN}[INFO]{C.NC}  {msg}")


def ok(msg: str) -> None:
    print(f"{C.GREEN}[ OK ]{C.NC} {msg}")


def warn(msg: str) -> None:
    print(f"{C.YELLOW}[WARN]{C.NC} {msg}")


def fail(msg: str) -> None:
    print(f"{C.RED}[FAIL]{C.NC} {msg}")
    sys.exit(1)


# ── Report formatting ────────────────────────────────────────────────────────

DIV = "─" * 76
SEC = "═" * 76


def header(title: str) -> str:
    return f"\n{SEC}\n  {title}\n{SEC}"


def section(title: str) -> str:
    return f"\n{DIV}\n  {title}\n{DIV}"
