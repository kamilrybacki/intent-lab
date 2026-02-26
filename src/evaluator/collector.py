"""Data collection from the Hallucinating Splines REST API with Redis caching."""

from __future__ import annotations

import json
import sys

from src.common.constants import HS_API
from src.common.http import api_get


def fetch_all_actions(city_id: str, limit: int = 500) -> list[dict]:
    """Paginate through ``/v1/cities/:id/actions``."""
    actions: list[dict] = []
    offset = 0
    while True:
        data = api_get(
            f"/v1/cities/{city_id}/actions?limit={limit}&offset={offset}",
            base_url=HS_API,
        )
        if not data:
            break
        batch = data.get("actions", [])
        actions.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return actions


def _try_redis_cache(city_id: str) -> dict | None:
    """Attempt to load full city data from Redis.  Returns None on miss."""
    try:
        from src.common.redis import get_redis
        r = get_redis()
        raw = r.get(f"city:{city_id}:full")
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None


def _store_redis_cache(city_id: str, data: dict) -> None:
    """Best-effort cache of the full city data blob in Redis."""
    try:
        from src.common.redis import get_redis
        r = get_redis()
        r.set(f"city:{city_id}:full", json.dumps(data, default=str))
    except Exception as exc:
        print(f"  Redis cache write failed (non-fatal): {exc}", file=sys.stderr)


def collect_city_data(city_id: str) -> dict:
    """Fetch all relevant datasets for a single city (Redis cache first)."""
    cached = _try_redis_cache(city_id)
    if cached:
        return cached

    stats = api_get(f"/v1/cities/{city_id}/stats", base_url=HS_API)
    summary = api_get(f"/v1/cities/{city_id}/map/summary", base_url=HS_API)
    history = api_get(f"/v1/cities/{city_id}/history", base_url=HS_API)
    snapshots = api_get(
        f"/v1/cities/{city_id}/snapshots?limit=500", base_url=HS_API
    )
    actions = fetch_all_actions(city_id)
    result = {
        "id": city_id,
        "stats": stats,
        "map_summary": summary,
        "history": history,
        "snapshots": snapshots.get("snapshots", []),
        "actions": actions,
    }
    _store_redis_cache(city_id, result)
    return result
