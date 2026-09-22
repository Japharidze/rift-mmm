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

from r3m.config import settings


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


def labelling_targets(
    conn: psycopg.Connection, champion_ids: Sequence[str] | None = None
) -> list[dict[str, str]]:
    """Champion x role pairs due a label, with the kit text to label them from.

    Reads champion_role_live rather than champion_role: the unit of labelling
    is every role a champion is genuinely played in (the 30% rule), not just
    the fixture-seeded primary. kit_text comes from the champion's current
    patch (champion.last_patch) — labelling always runs against the latest
    ingested kit, never a stale one a re-ingest has since moved past.
    """
    where = ""
    params: tuple[Any, ...] = ()
    if champion_ids:
        where = "where cr.champion_id = any(%s)"
        params = (list(champion_ids),)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            select cr.champion_id, cr.role::text, c.name, c.title, cp.kit_text
            from champion_role_live cr
            join champion c on c.id = cr.champion_id
            join champion_patch cp
                on cp.champion_id = c.id and cp.patch_version = c.last_patch
            {where}
            order by cr.champion_id, cr.role
            """,
            params,
        )
        cols = ("champion_id", "role", "name", "title", "kit_text")
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def insert_label_run(
    conn: psycopg.Connection, *, prompt_version: str, model: str, note: str | None = None
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into label_run (prompt_version, model, note)
            values (%s, %s, %s)
            returning id
            """,
            (prompt_version, model, note),
        )
        return cur.fetchone()[0]  # type: ignore[index]


# The ten sub-traits plus the three aggregates. Order matches
# r3m.labeling.schema.ChampionLabel's fields, but this module does not
# import that class — labelling code goes through db.py, not the other way
# round, so this takes a plain mapping instead.
CHAMPION_LABEL_COLUMNS = (
    "micro_precision", "micro_execution", "micro_cheat",
    "meso_deception", "meso_prediction", "meso_exploitation", "meso_cheat",
    "macro_routing", "macro_win_condition", "macro_cheat",
    "micro", "meso", "macro",
    "rationale",
)

_CHAMPION_LABEL_INSERT = """
    insert into champion_label (
        label_run_id, champion_id, role, {columns}, raw_response
    )
    values (%s, %s, %s::role_t, {placeholders}, %s)
""".format(
    columns=", ".join(CHAMPION_LABEL_COLUMNS),
    placeholders=", ".join(["%s"] * len(CHAMPION_LABEL_COLUMNS)),
)


def insert_champion_label(
    conn: psycopg.Connection,
    *,
    label_run_id: int,
    champion_id: str,
    role: str,
    fields: Mapping[str, Any],
    raw_response: dict[str, Any],
) -> None:
    """fields must carry every name in CHAMPION_LABEL_COLUMNS; raw_response is
    the full structured-output payload, kept so a row can be reviewed or
    replayed without another model call."""
    with conn.cursor() as cur:
        cur.execute(
            _CHAMPION_LABEL_INSERT,
            (
                label_run_id,
                champion_id,
                role,
                *(fields[col] for col in CHAMPION_LABEL_COLUMNS),
                Jsonb(raw_response),
            ),
        )


def latest_label_run(conn: psycopg.Connection) -> int | None:
    """The most recent run that actually produced labels.

    Not simply max(id): a run that labelled nothing leaves no row now, but
    older databases may still hold one, and "latest run" must never mean an
    empty one.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            select r.id from label_run r
            join champion_label l on l.label_run_id = r.id
            group by r.id order by r.id desc limit 1
            """
        )
        row = cur.fetchone()
        return row[0] if row else None


def label_run_scores(
    conn: psycopg.Connection, label_run_id: int
) -> list[dict[str, Any]]:
    """The three aggregates per champion x role for one run."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select l.champion_id, l.role, l.micro, l.meso, l.macro,
                   r.prompt_version, r.model
            from champion_label l
            join label_run r on r.id = l.label_run_id
            where l.label_run_id = %s
            order by l.champion_id
            """,
            (label_run_id,),
        )
        return [
            {
                "champion_id": r[0],
                "role": r[1],
                "micro": float(r[2]),
                "meso": float(r[3]),
                "macro": float(r[4]),
                "prompt_version": r[5],
                "model": r[6],
            }
            for r in cur.fetchall()
        ]


def replace_match_data_roles(conn: psycopg.Connection) -> int:
    """Write champion_role from champion_role_live.

    Replaces rather than appends: champion_role describes which roles are
    currently played, so a role that has fallen below the threshold should
    leave. Only source='match_data' rows are touched, so a hand-curated
    fixture row would survive. Labels are unaffected -- champion_label carries
    its own role column rather than pointing here.

    is_primary is the highest share, broken by role name when two are exactly
    equal. The tie-break is arbitrary but deterministic, and it has to exist:
    champion_role_one_primary allows exactly one primary per champion, and
    Yone sits at top 0.50 / mid 0.49.
    """
    with conn.cursor() as cur:
        cur.execute("delete from champion_role where source = 'match_data'")
        cur.execute(
            """
            insert into champion_role (champion_id, role, is_primary, source)
            select
                champion_id,
                role,
                row_number() over (
                    partition by champion_id order by share desc, role
                ) = 1,
                'match_data'
            from champion_role_live
            """
        )
        return cur.rowcount


def champion_points(
    conn: psycopg.Connection, prompt_version: str | None = None
) -> list[dict[str, Any]]:
    """Every champion x role as an MMM point, one row each.

    Scoped to a single prompt version -- by default whichever the most recent
    run used -- because scores from different wordings are not comparable and
    mixing them would quietly blend two spaces. Within that version the latest
    label per champion x role wins, which is what makes a gap-filling run
    (label_run 10 over 9) union correctly instead of double-counting.
    """
    with conn.cursor() as cur:
        if prompt_version is None:
            cur.execute(
                """
                select r.prompt_version from label_run r
                join champion_label l on l.label_run_id = r.id
                group by r.id, r.prompt_version order by r.id desc limit 1
                """
            )
            row = cur.fetchone()
            if row is None:
                return []
            prompt_version = row[0]

        cur.execute(
            """
            select distinct on (l.champion_id, l.role)
                   l.champion_id, c.name, l.role, l.micro, l.meso, l.macro
            from champion_label l
            join label_run r on r.id = l.label_run_id
            join champion c on c.id = l.champion_id
            where r.prompt_version = %s
            order by l.champion_id, l.role, l.label_run_id desc
            """,
            (prompt_version,),
        )
        return [
            {
                "champion_id": r[0],
                "name": r[1],
                "role": r[2],
                "micro": float(r[3]),
                "meso": float(r[4]),
                "macro": float(r[5]),
                "prompt_version": prompt_version,
            }
            for r in cur.fetchall()
        ]
