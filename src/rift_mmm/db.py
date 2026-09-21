"""Database gateway.

Every write to Postgres goes through here — no other module builds SQL.
Functions take an open connection and never commit: the caller owns the
transaction boundary, so one ingest run is one transaction.

Champion fields are keyword-only. `name`, `title` and `partype` are all text
and adjacent, so positional arguments would let a swap through silently.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from rift_mmm.config import settings


def connect() -> psycopg.Connection:
    """Open a connection. Usable as a context manager — commits on clean exit."""
    return psycopg.connect(settings.db_url)


def upsert_patch(conn: psycopg.Connection, version: str) -> None:
    """Record a Data Dragon version.

    Idempotent, and deliberately does not touch ingested_at on conflict: the
    column means "when we first pulled this patch", so a re-run keeps it.
    """
    with conn.cursor() as cur:
        cur.execute(
            "insert into patch (version) values (%s) on conflict (version) do nothing",
            (version,),
        )


def upsert_champion(
    conn: psycopg.Connection,
    *,
    champion_id: str,
    riot_key: int,
    name: str,
    title: str,
    tags: list[str],
    partype: str,
    patch_version: str,
) -> None:
    """Insert or refresh a champion's identity row.

    first_patch is set on insert and never updated — it is absent from the SET
    list on purpose. last_patch advances to the patch being ingested, which
    assumes patches arrive in ascending order. Backfilling an older patch would
    need a version-aware comparison, since these strings do not sort correctly
    ('9.24.1' > '16.18.1' lexically).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into champion (
                id, riot_key, name, title, tags, partype, first_patch, last_patch
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (id) do update set
                riot_key   = excluded.riot_key,
                name       = excluded.name,
                title      = excluded.title,
                tags       = excluded.tags,
                partype    = excluded.partype,
                last_patch = excluded.last_patch
            """,
            (
                champion_id,
                riot_key,
                name,
                title,
                tags,
                partype,
                patch_version,
                patch_version,
            ),
        )


def upsert_champion_patch(
    conn: psycopg.Connection,
    *,
    champion_id: str,
    patch_version: str,
    raw: dict[str, Any],
    kit_text: str,
) -> None:
    """Store one champion's Data Dragon entry for one patch.

    Upsert rather than plain insert so re-running an ingest is idempotent, and
    so a revised cleaner can rewrite kit_text against the stored raw entry
    without refetching the patch.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into champion_patch (champion_id, patch_version, raw, kit_text)
            values (%s, %s, %s, %s)
            on conflict (champion_id, patch_version) do update set
                raw      = excluded.raw,
                kit_text = excluded.kit_text
            """,
            (champion_id, patch_version, Jsonb(raw), kit_text),
        )


def count_matches(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("select count(*) from match")
        return cur.fetchone()[0]  # type: ignore[index]


def known_match_ids(conn: psycopg.Connection, match_ids: list[str]) -> set[str]:
    """Which of these are already stored. The crawl is resumable through this:
    a re-run skips everything it already has rather than refetching."""
    if not match_ids:
        return set()
    with conn.cursor() as cur:
        cur.execute("select match_id from match where match_id = any(%s)", (match_ids,))
        return {row[0] for row in cur.fetchall()}


def insert_match(
    conn: psycopg.Connection,
    *,
    match_id: str,
    platform: str,
    queue_id: int,
    game_version: str,
    duration_s: int,
    played_at: datetime,
    seed_tier: str,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into match (
                match_id, platform, queue_id, game_version,
                duration_s, played_at, seed_tier
            )
            values (%s, %s, %s, %s, %s, %s, %s)
            on conflict (match_id) do nothing
            """,
            (match_id, platform, queue_id, game_version, duration_s, played_at, seed_tier),
        )


# Built once so the column list, the placeholders and the row keys cannot drift
# apart. sample.py maps Riot's names onto these.
PARTICIPANT_COLUMNS = (
    "puuid",
    "champion_key",
    "champion_name",
    "team_position",
    "win",
    "kills",
    "deaths",
    "assists",
    "skillshots_hit",
    "skillshots_dodged",
    "skillshots_dodged_small_window",
    "ability_uses",
    "vision_score_per_minute",
    "control_wards_placed",
    "turret_plates_taken",
    "teleport_takedowns",
    "dragon_takedowns",
    "baron_takedowns",
    "outnumbered_kills",
    "unseen_recalls",
    "kill_after_hidden_with_ally",
)

_PARTICIPANT_INSERT = """
    insert into match_participant (match_id, {columns})
    values (%s, {placeholders})
    on conflict (match_id, puuid) do nothing
""".format(
    columns=", ".join(PARTICIPANT_COLUMNS),
    placeholders=", ".join(["%s"] * len(PARTICIPANT_COLUMNS)),
)


def insert_match_participants(
    conn: psycopg.Connection,
    match_id: str,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    """Ten rows per match, written in one round trip.

    Rows are keyed by PARTICIPANT_COLUMNS; a missing metric is None rather than
    absent, since Riot omits fields that never applied in a given game.
    """
    with conn.cursor() as cur:
        cur.executemany(
            _PARTICIPANT_INSERT,
            [
                (match_id, *(r.get(col) for col in PARTICIPANT_COLUMNS))
                for r in rows
            ],
        )
