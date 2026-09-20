"""HTTP fetching: timeouts, retries, and backoff.

Deliberately knows nothing about Data Dragon or any other source — it only
knows how to ask for a URL politely. A second source adds its rate limiting
here rather than growing a client of its own.
"""

import time
from typing import Any

import httpx

TIMEOUT = httpx.Timeout(10.0, connect=5.0)
USER_AGENT = "rift-mmm/0.1"

MAX_ATTEMPTS = 4
BACKOFF_BASE = 0.5  # seconds, doubled after each failed attempt
MAX_BACKOFF = 8.0

# Transient by convention. Everything else in 4xx is the caller's mistake and
# retrying it just wastes time.
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})

_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    # Reused across calls: one ingest makes ~170 sequential requests to the
    # same host, and a fresh TLS handshake per request dominates the runtime.
    global _client
    if _client is None:
        _client = httpx.Client(
            timeout=TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
    return _client


def close() -> None:
    """Release the shared connection pool. Safe to call more than once."""
    global _client
    if _client is not None:
        _client.close()
        _client = None


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None  # HTTP-date form; fall back to our own backoff


def get_json(url: str) -> Any:
    """Fetch and parse JSON, retrying transient failures."""
    client = _get_client()
    delay = BACKOFF_BASE
    last_error: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        wait = delay
        try:
            response = client.get(url)
        except httpx.TransportError as exc:
            last_error = exc
        else:
            if response.status_code not in RETRY_STATUS:
                response.raise_for_status()
                return response.json()
            last_error = httpx.HTTPStatusError(
                f"{response.status_code} from {url}",
                request=response.request,
                response=response,
            )
            wait = _retry_after(response) or delay

        if attempt == MAX_ATTEMPTS:
            break
        time.sleep(min(wait, MAX_BACKOFF))
        delay *= 2

    assert last_error is not None  # the loop always runs at least once
    raise last_error
