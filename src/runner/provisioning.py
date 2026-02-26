"""HS key provisioning, city lifecycle, and workspace preparation."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path

from src.common.constants import HS_API, INTENTS_DIR, TEMPLATES_DIR
from src.common.http import http_delete, http_post
from src.runner.agent import Agent


_CITY_DELAY = 1.0  # seconds between city API calls


def provision_hs_key() -> str:
    """Create a new Hallucinating Splines API key."""
    data = http_post(f"{HS_API}/v1/keys")
    key = data.get("key") or data.get("api_key") or ""
    if not key:
        raise RuntimeError(f"Unexpected key response: {data}")
    return key


def _auth(hs_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {hs_key}"}


def create_city(hs_key: str, seed: int | None = None) -> str:
    """Create a new city under the given HS key and return its ID."""
    body = json.dumps({"seed": seed} if seed is not None else {}).encode()
    data = http_post(
        f"{HS_API}/v1/cities",
        headers={**_auth(hs_key), "Content-Type": "application/json"},
        body=body,
        timeout=30,
    )
    city_id = data.get("id") or data.get("city_id") or ""
    if not city_id:
        raise RuntimeError(f"No city ID in response: {data}")
    return city_id


def retire_city(hs_key: str, city_id: str) -> None:
    """Retire (DELETE) a city to free up a slot on the key."""
    http_delete(
        f"{HS_API}/v1/cities/{city_id}",
        headers=_auth(hs_key),
        timeout=15,
    )


def create_pair(hs_key: str) -> tuple[str, str]:
    """Create two cities under one key.  Returns (city_a_id, city_b_id)."""
    city_a = create_city(hs_key)
    time.sleep(_CITY_DELAY)
    city_b = create_city(hs_key)
    return city_a, city_b


def retire_pair(hs_key: str, city_a_id: str, city_b_id: str) -> None:
    """Retire both cities of a pair to free slots for the next round."""
    retire_city(hs_key, city_a_id)
    time.sleep(_CITY_DELAY)
    retire_city(hs_key, city_b_id)


def prepare_workspace(agent: Agent) -> Path:
    """Build an isolated workspace for one agent from the templates + intents."""
    workspace = Path(tempfile.mkdtemp(prefix=f"intent-{agent.agent_id}-"))

    # Copy template files (CLAUDE.md, .claude/mcp.json)
    shutil.copytree(TEMPLATES_DIR, workspace, dirs_exist_ok=True)

    # Copy the correct intent file
    src_intent = INTENTS_DIR / agent.intent_file
    shutil.copy2(src_intent, workspace / agent.intent_file)

    # Inject the agent-specific HS API key into .claude/mcp.json
    mcp_path = workspace / ".claude" / "mcp.json"
    mcp_path.write_text(
        mcp_path.read_text().replace("HS_API_KEY_PLACEHOLDER", agent.hs_key)
    )

    # Inject the pre-created city ID into CLAUDE.md
    claude_md = workspace / "CLAUDE.md"
    claude_md.write_text(
        claude_md.read_text().replace("CITY_ID_PLACEHOLDER", agent.city_id)
    )

    return workspace
