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

# Docker — pin to a specific tag; update deliberately
DOCKER_IMAGE = "claude-code:local"

# ── Simulation timing (single source of truth) ──────────────────────────────
SIM_TOTAL_CYCLES = 50           # number of months to simulate
SIM_TICK_INTERVAL = 15          # seconds between time advances
SIM_DURATION_MINS = (SIM_TOTAL_CYCLES * SIM_TICK_INTERVAL) / 60

# Agent prompt (auto-derived from simulation config)
AGENT_PROMPT = (
    "Your city already exists — do NOT create a new one. "
    f"Time advances automatically every ~{SIM_TICK_INTERVAL} seconds — do NOT call advance_time yourself. "
    "Begin building immediately and focus on zoning, infrastructure, and city management. "
    f"You have {SIM_TOTAL_CYCLES} cycles (~{SIM_DURATION_MINS:.0f} minutes of real time)."
)

# Agent guardrails
AGENT_MAX_TURNS = 450
AGENT_TIMEOUT_SECS = int(SIM_DURATION_MINS * 60) + 5 * 60  # sim duration + 5 min margin
