"""Match sampling: crawl ranked solo games into the match tables.

Unlike ingest, this commits per match instead of in one transaction. A crawl
runs for tens of minutes, a development key expires every 24 hours, and the
rows are additive — a partial sample is still useful, and a resumed run skips
whatever is already stored.

This produces no labels. Its output is the position distribution behind
champion_role, plus the raw material for drift signals.
"""

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from itertools import zip_longest
from datetime import UTC, datetime
from typing import Any

from rift_mmm import db
from rift_mmm.riot_api import QUEUE_RANKED_SOLO, RiotApi

# Mid-ladder on purpose. The product targets newcomers, so the high-elo meta is
# the wrong place to learn role splits from. seed_tier is stored per match so
# the assumption stays checkable.
DEFAULT_SEEDS = (("EMERALD", "II"), ("PLATINUM", "II"), ("GOLD", "II"))

MATCH_IDS_PER_PLAYER = 20

# The challenge fields kept, and the column each lands in. Chosen as validation
# signal for the three dimensions — never as labelling input. Rates are computed
# later against match.duration_s, so no denominator is stored.
CHALLENGE_FIELDS = {
    "skillshots_hit": "skillshotsHit",
    "skillshots_dodged": "skillshotsDodged",
    "skillshots_dodged_small_window": "dodgeSkillShotsSmallWindow",
    "ability_uses": "abilityUses",
    "vision_score_per_minute": "visionScorePerMinute",
    "control_wards_placed": "controlWardsPlaced",
    "turret_plates_taken": "turretPlatesTaken",
    "teleport_takedowns": "teleportTakedowns",
    "dragon_takedowns": "dragonTakedowns",
    "baron_takedowns": "baronTakedowns",
    "outnumbered_kills": "outnumberedKills",
    "unseen_recalls": "unseenRecalls",
    "kill_after_hidden_with_ally": "killAfterHiddenWithAlly",
}


@dataclass(frozen=True)
class SampleResult:
    stored: int      # matches added by this run
    total: int       # matches in the database afterwards
    requests: int    # API calls spent


def _duration_s(info: dict[str, Any]) -> int:
    seconds = info["gameDuration"]
    # Riot reported this in milliseconds for matches predating gameEndTimestamp.
    # No game runs to 10,000 seconds, so the magnitude disambiguates it safely.
    return seconds // 1000 if seconds > 10_000 else seconds


def _challenge_columns(participant: dict[str, Any]) -> dict[str, Any]:
    challenges = participant.get("challenges") or {}
    return {col: challenges.get(key) for col, key in CHALLENGE_FIELDS.items()}


def _participant_rows(info: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "puuid": p["puuid"],
            "champion_key": p["championId"],
            "champion_name": p["championName"],
            # Empty on remakes and odd comps. Kept raw and dropped in the view,
            # rather than guessed at here.
            "team_position": p.get("teamPosition", ""),
            "win": p["win"],
            "kills": p["kills"],
            "deaths": p["deaths"],
            "assists": p["assists"],
            **_challenge_columns(p),
        }
        for p in info["participants"]
    ]


def run(
    api: RiotApi,
    *,
    target: int,
    seeds: Sequence[tuple[str, str]] = DEFAULT_SEEDS,
    progress: Callable[[int, int], None] | None = None,
) -> SampleResult:
    """Crawl until the database holds `target` matches.

    `target` is a total, not a quantity to add, so topping a 2k sample up to 5k
    is the same command with a bigger number.
    """
    requests = 0
    stored = 0

    with db.connect() as conn:
        total = db.count_matches(conn)
        if total >= target:
            return SampleResult(stored=0, total=total, requests=0)

        saw_puuid = False

        def seeded_players() -> Iterator[tuple[str, str]]:
            """Yield (puuid, tier) round-robin across the seeds.

            Walking the seeds in order would let the first tier supply the whole
            sample before the others were touched — which is exactly what
            happened on the first 2k run, where every match came from EMERALD.
            Interleaving per player rather than per page is what makes the mix
            actually hold.
            """
            nonlocal requests
            page = 1
            while True:
                ladders: list[list[tuple[str, str]]] = []
                for tier, division in seeds:
                    entries = api.league_entries(tier, division, page)
                    requests += 1
                    ladders.append(
                        [(e["puuid"], tier) for e in entries if e.get("puuid")]
                    )
                if not any(ladders):
                    return
                for row in zip_longest(*ladders):
                    for player in row:
                        if player is not None:
                            yield player
                page += 1

        for puuid, tier in seeded_players():
            if total >= target:
                break
            saw_puuid = True

            match_ids = api.match_ids(puuid, count=MATCH_IDS_PER_PLAYER)
            requests += 1
            known = db.known_match_ids(conn, match_ids)

            for match_id in match_ids:
                if total >= target or match_id in known:
                    continue

                data = api.match(match_id)
                requests += 1
                info = data["info"]

                # match_ids was queue-filtered, but a mismatch here would
                # silently poison the position data, so check anyway.
                if info.get("queueId") != QUEUE_RANKED_SOLO:
                    continue

                db.insert_match(
                    conn,
                    match_id=data["metadata"]["matchId"],
                    platform=info["platformId"],
                    queue_id=info["queueId"],
                    game_version=info["gameVersion"],
                    duration_s=_duration_s(info),
                    played_at=datetime.fromtimestamp(
                        info["gameStartTimestamp"] / 1000, tz=UTC
                    ),
                    seed_tier=tier,
                )
                db.insert_match_participants(
                    conn, data["metadata"]["matchId"], _participant_rows(info)
                )
                # Per match, so an interrupted crawl keeps what it has.
                conn.commit()

                total += 1
                stored += 1
                if progress is not None:
                    progress(total, target)

        if not saw_puuid and stored == 0:
            raise RuntimeError(
                "No ladder entry carried a puuid, so no player could be crawled. "
                "league-v4 entries have changed shape before; check what the "
                "response actually contains."
            )

    return SampleResult(stored=stored, total=total, requests=requests)
