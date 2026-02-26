"""Structured logging configuration (structlog)."""

from __future__ import annotations

import logging
from pathlib import Path

import structlog


def configure_structlog() -> None:
    """Configure structlog for human-readable console output.

    Call once at process startup.
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_json_file_logger(log_path: Path) -> structlog.BoundLogger:
    """Return a structlog logger that writes JSON lines to *log_path*.

    Creates an independent logger backed by a stdlib FileHandler,
    bypassing the global console configuration.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(str(log_path), mode="a")
    file_handler.setLevel(logging.DEBUG)

    stdlib_logger = logging.getLogger(f"structlog.{log_path}")
    stdlib_logger.handlers = [file_handler]
    stdlib_logger.setLevel(logging.DEBUG)
    stdlib_logger.propagate = False

    return structlog.wrap_logger(
        stdlib_logger,
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )
