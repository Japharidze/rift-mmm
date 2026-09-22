"""Riot API client — the source of the match sample.

Riot uses two routing schemes and mixing them up is the usual first bug:
platform hosts (euw1, na1) serve league and summoner data, regional hosts
(europe, americas) serve match-v5.

Rate limiting lives in fetch.RateLimiter. The budget is per key, so one limiter
is shared across every endpoint on a client rather than one per method.
"""

from typing import Any

from r3m import fetch
from r3m.config import settings

QUEUE_RANKED_SOLO = 420
RANKED_SOLO = "RANKED_SOLO_5x5"

# Development key limits, both enforced at once. Held slightly under the real
# 100/120s: a limiter starts each process with an empty window while Riot's
# is still counting requests from the previous run, so full speed trips a 429
# at every boundary. Retry-After recovers from one, but not paying for it is
# cheaper than recovering.
DEV_KEY_WINDOWS = ((20, 1.0), (95, 120.0))

PLATFORM_REGION = {
    "euw1": "europe", "eun1": "europe", "tr1": "europe", "ru": "europe", "me1": "europe",
    "na1": "americas", "br1": "americas", "la1": "americas", "la2": "americas",
    "kr": "asia", "jp1": "asia",
    "oc1": "sea", "ph2": "sea", "sg2": "sea", "th2": "sea", "tw2": "sea", "vn2": "sea",
}


class RiotApi:
    def __init__(self, platform: str = "euw1", api_key: str | None = None) -> None:
        key = settings.riot_api_key if api_key is None else api_key
        if not key:
            raise RuntimeError(
                "RIOT_API_KEY is not set. Development keys expire every 24 hours "
                "and are regenerated at developer.riotgames.com."
            )
        if platform not in PLATFORM_REGION:
            raise ValueError(f"unknown platform {platform!r}")

        self.platform = platform
        self.region = PLATFORM_REGION[platform]
        self._headers = {"X-Riot-Token": key}
        self._limiter = fetch.RateLimiter(DEV_KEY_WINDOWS)

    def _get(self, url: str) -> Any:
        return fetch.get_json(url, headers=self._headers, limiter=self._limiter)

    def league_entries(self, tier: str, division: str, page: int = 1) -> list[dict[str, Any]]:
        """One page of ranked ladder entries — the seed for the crawl."""
        return self._get(
            f"https://{self.platform}.api.riotgames.com/lol/league/v4/entries/"
            f"{RANKED_SOLO}/{tier}/{division}?page={page}"
        )

    def match_ids(
        self,
        puuid: str,
        *,
        count: int = 20,
        start: int = 0,
        queue: int = QUEUE_RANKED_SOLO,
    ) -> list[str]:
        """Recent match ids for one player. Queue-filtered: an unfiltered call
        returns ARAM and normals, which carry no usable position."""
        return self._get(
            f"https://{self.region}.api.riotgames.com/lol/match/v5/matches/"
            f"by-puuid/{puuid}/ids?queue={queue}&start={start}&count={count}"
        )

    def match(self, match_id: str) -> dict[str, Any]:
        """One match. This is the expensive call — one request per match."""
        return self._get(
            f"https://{self.region}.api.riotgames.com/lol/match/v5/matches/{match_id}"
        )
