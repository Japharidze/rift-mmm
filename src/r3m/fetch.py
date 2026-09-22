"""HTTP fetching: timeouts, retries, and backoff.

Deliberately knows nothing about Data Dragon or any other source — it only
knows how to ask for a URL politely. A second source adds its rate limiting
here rather than growing a client of its own.
"""

import time
from collections import deque
from collections.abc import Sequence
from typing import Any

import httpx

TIMEOUT = httpx.Timeout(10.0, connect=5.0)
USER_AGENT = "r3m/0.1"

MAX_ATTEMPTS = 6
BACKOFF_BASE = 0.5  # seconds, doubled after each failed attempt
MAX_BACKOFF = 8.0
# A server that says Retry-After is telling us when its window reopens, and
# that is not ours to shorten. Capped only so a hostile value cannot hang the
# process; MAX_BACKOFF applies to our own guesses, never to this.
MAX_RETRY_AFTER = 180.0

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


class RateLimiter:
    """Sliding-window limiter honouring several windows at once.

    Riot enforces two simultaneously (20 per second and 100 per two minutes),
    and the tighter one changes depending on how long the run has been going,
    so both have to be tracked rather than just the smaller rate.
    """

    def __init__(self, windows: Sequence[tuple[int, float]]) -> None:
        self._windows = [(limit, seconds, deque[float]()) for limit, seconds in windows]

    def acquire(self) -> None:
        while True:
            now = time.monotonic()
            wait = 0.0
            for limit, seconds, hits in self._windows:
                while hits and now - hits[0] >= seconds:
                    hits.popleft()
                if len(hits) >= limit:
                    wait = max(wait, seconds - (now - hits[0]))
            if wait <= 0:
                break
            time.sleep(wait)

        now = time.monotonic()
        for _, _, hits in self._windows:
            hits.append(now)


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None  # HTTP-date form; fall back to our own backoff


def get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    limiter: RateLimiter | None = None,
) -> Any:
    """Fetch and parse JSON, retrying transient failures.

    A limiter, when given, is consumed once per attempt rather than once per
    call: a retry is another request as far as the server is concerned.
    """
    client = _get_client()
    delay = BACKOFF_BASE
    last_error: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        wait = min(delay, MAX_BACKOFF)
        if limiter is not None:
            limiter.acquire()
        try:
            response = client.get(url, headers=headers)
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
            retry_after = _retry_after(response)
            if retry_after is not None:
                # Honoured in full. Clamping it to our own backoff just retries
                # into a window the server already said is shut.
                wait = min(retry_after, MAX_RETRY_AFTER)

        if attempt == MAX_ATTEMPTS:
            break
        time.sleep(wait)
        delay *= 2

    assert last_error is not None  # the loop always runs at least once
    raise last_error
