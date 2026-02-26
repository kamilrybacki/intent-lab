"""Agent data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Agent:
    """Manifest for a single experiment agent."""

    agent_id: str                # e.g. "a-03", "b-07"
    intent: str                  # "a" or "b"
    intent_file: str             # filename inside the workspace, e.g. "intent_a.txt"
    label: str                   # human-readable label
    hs_key: str = ""             # provisioned Hallucinating Splines API key
    city_id: str = ""            # discovered after agent finishes
    workspace: Path = field(default_factory=lambda: Path())
    status: str = "pending"      # pending | running | completed | failed
