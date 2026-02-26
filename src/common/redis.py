"""Redis connection and data-access helpers for persistent experiment storage."""

from __future__ import annotations

import json
import os

import redis


_REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
_REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
_REDIS_DB = int(os.environ.get("REDIS_DB", "0"))
_REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "intent-experiment")

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """Return a shared Redis client (lazy singleton)."""
    global _client
    if _client is None:
        _client = redis.Redis(
            host=_REDIS_HOST,
            port=_REDIS_PORT,
            db=_REDIS_DB,
            password=_REDIS_PASSWORD,
            decode_responses=True,
        )
    return _client


# ── HS key pool ──────────────────────────────────────────────────────────────


def store_hs_key(key: str) -> None:
    """Append *key* to the HS key pool."""
    get_redis().rpush("hs:keys", key)


def peek_hs_key() -> str | None:
    """Return the first key without removing it."""
    return get_redis().lindex("hs:keys", 0)


# ── Experiment metadata ──────────────────────────────────────────────────────


def store_experiment(exp_id: str, meta: dict) -> None:
    """Persist experiment metadata and add to the chronological index."""
    r = get_redis()
    r.hset(f"experiment:{exp_id}", mapping={
        k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
        for k, v in meta.items()
    })
    timestamp = meta.get("timestamp_unix", 0)
    r.zadd("experiments", {exp_id: float(timestamp)})


def get_experiment(exp_id: str) -> dict:
    """Retrieve experiment metadata."""
    raw = get_redis().hgetall(f"experiment:{exp_id}")
    result: dict = {}
    for k, v in raw.items():
        try:
            result[k] = json.loads(v)
        except (json.JSONDecodeError, TypeError):
            result[k] = v
    return result


def get_all_experiments() -> list[str]:
    """Return all experiment IDs ordered chronologically (oldest first)."""
    return get_redis().zrange("experiments", 0, -1)


# ── Agent results ────────────────────────────────────────────────────────────


def store_agent_result(exp_id: str, agent_dict: dict) -> None:
    """Append an agent record to the experiment's agent list."""
    get_redis().rpush(f"experiment:{exp_id}:agents", json.dumps(agent_dict))


def get_agent_results(exp_id: str) -> list[dict]:
    """Return all agent records for an experiment."""
    raw = get_redis().lrange(f"experiment:{exp_id}:agents", 0, -1)
    return [json.loads(r) for r in raw]
