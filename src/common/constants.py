"""Shared constants for the Intent Engineering experiment."""

from pathlib import Path

# Project root = intent-experiment/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Asset paths
ASSETS_DIR = PROJECT_ROOT / "assets"
TEMPLATES_DIR = ASSETS_DIR / "templates"
INTENTS_DIR = ASSETS_DIR / "intents"

# Hallucinating Splines
HS_API = "https://api.hallucinatingsplines.com"

# claude-code-router
CCR_HOST = "host.docker.internal"
CCR_PORT = 3456

# Docker — pin to a specific tag; update deliberately
DOCKER_IMAGE = "claude-code:local"

# Agent prompt
AGENT_PROMPT = (
    "Your city already exists — do NOT create a new one. "
    "Time advances automatically every ~30 seconds — do NOT call advance_time yourself. "
    "Begin building immediately and focus on zoning, infrastructure, and city management. "
    "You have 150 cycles (~75 minutes of real time)."
)

# Agent guardrails
AGENT_MAX_TURNS = 450         # max agentic round-trips per agent
AGENT_TIMEOUT_SECS = 80 * 60  # hard wall-clock timeout (80 minutes, covers 150×30s + margin)
