"""Lightweight HTTP helpers (stdlib only)."""

from __future__ import annotations

import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_UA = "IntentExperiment/1.0"
_MAX_RETRIES = 5
_BACKOFF_BASE = 2.0  # seconds; doubles each retry


def _request(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict | None = None,
    timeout: int = 15,
    retries: int = _MAX_RETRIES,
) -> dict:
    """Core request with User-Agent and retry-on-429."""
    hdr = {"Accept": "application/json", "User-Agent": _UA, **(headers or {})}
    req = Request(url, method=method, data=data, headers=hdr)
    for attempt in range(1, retries + 1):
        try:
            with urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode()
                return json.loads(body) if body else {}
        except HTTPError as exc:
            if exc.code == 429 and attempt < retries:
                wait = _BACKOFF_BASE ** attempt
                print(
                    f"  Rate-limited ({url}), retrying in {wait:.0f}s "
                    f"(attempt {attempt}/{retries}) ...",
                    file=sys.stderr,
                )
                time.sleep(wait)
                continue
            raise
    return {}  # unreachable, keeps mypy happy


def http_get(url: str, headers: dict | None = None, timeout: int = 15) -> dict:
    """Perform a GET request and return the parsed JSON body."""
    return _request(url, method="GET", headers=headers, timeout=timeout)


def http_post(
    url: str,
    headers: dict | None = None,
    body: bytes | None = None,
    timeout: int = 15,
) -> dict:
    """Perform a POST request and return the parsed JSON body."""
    return _request(
        url, method="POST", data=body if body is not None else b"",
        headers=headers, timeout=timeout,
    )


def http_delete(url: str, headers: dict | None = None, timeout: int = 15) -> dict:
    """Perform a DELETE request and return the parsed JSON body."""
    return _request(url, method="DELETE", data=b"", headers=headers, timeout=timeout)


def api_get(path: str, *, base_url: str, timeout: int = 30) -> dict:
    """GET a path relative to a base URL (for evaluation API calls)."""
    url = f"{base_url}{path}"
    try:
        return _request(url, method="GET", timeout=timeout)
    except (HTTPError, URLError) as exc:
        print(f"  API error: {url}\n    {exc}", file=sys.stderr)
        return {}
