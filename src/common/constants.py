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
    "Begin building immediately and execute your 50 simulation cycles "
    "to achieve your objective."
)

# Agent guardrails
AGENT_MAX_TURNS = 200        # max agentic round-trips per agent
AGENT_TIMEOUT_SECS = 30 * 60  # hard wall-clock timeout (30 minutes)
