"""Data Dragon: Riot's static champion CDN.

Returns entries exactly as Riot ships them. Type coercion and kit-text
cleaning happen downstream, so what lands in champion_patch.raw stays a
faithful copy of the patch.
"""

from collections.abc import Iterator
from typing import Any

from rift_mmm.fetch import get_json

BASE = "https://ddragon.leagueoflegends.com"
LOCALE = "en_US"  # the labelling prompt reads English kit prose


def versions() -> list[str]:
    """Every published version, newest first."""
    return get_json(f"{BASE}/api/versions.json")


def latest_version() -> str:
    return versions()[0]


def champion_ids(version: str) -> list[str]:
    """Champion ids for a patch, e.g. 'Karthus'. Sorted, for a stable ingest order."""
    payload = get_json(f"{BASE}/cdn/{version}/data/{LOCALE}/champion.json")
    return sorted(payload["data"])


def champion(version: str, champion_id: str) -> dict[str, Any]:
    """One champion's full entry, including passive and the four spells.

    The list endpoint carries identity fields but no spell text, so this
    per-champion call is the only source of kit prose — hence one request per
    champion rather than one per patch.

    Raises httpx.HTTPStatusError with status 403 (not 404) for an unknown id:
    Data Dragon is S3-backed and hides missing keys.
    """
    url = f"{BASE}/cdn/{version}/data/{LOCALE}/champion/{champion_id}.json"
    data = get_json(url)["data"]
    # Keyed by champion id, always exactly one entry. Taken by value rather
    # than by id because older patches shipped files whose data key differed
    # in case from the filename (FiddleSticks / Fiddlesticks).
    return next(iter(data.values()))


def champions(version: str) -> Iterator[tuple[str, dict[str, Any]]]:
    """Every champion's full entry for a patch, in id order.

    One request per champion, so ~170 requests and ~20s per patch.
    """
    for champion_id in champion_ids(version):
        yield champion_id, champion(version, champion_id)
