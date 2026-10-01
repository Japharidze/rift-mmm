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
    conn: psycopg.Connection,
    *,
    prompt_version: str,
    model: str,
    effort: str | None = None,
    note: str | None = None,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into label_run (prompt_version, model, effort, note)
            values (%s, %s, %s, %s)
            returning id
            """,
            (prompt_version, model, effort, note),
        )
        return cur.fetchone()[0]  # type: ignore[index]


# The ten sub-traits plus the three aggregates. Order matches
# r3m.labeling.schema.ChampionLabel's fields, but this module does not
# import that class — labelling code goes through db.py, not the other way
# round, so this takes a plain mapping instead.
# macro_win_condition and macro_resources occupy one slot: a run asks for
# exactly one and stores null for the other (migration 010). Both are listed
# so the insert is version-agnostic.
CHAMPION_LABEL_COLUMNS = (
    "micro_precision", "micro_execution", "micro_cheat",
    "meso_deception", "meso_prediction", "meso_exploitation", "meso_cheat",
    "macro_routing", "macro_win_condition", "macro_resources", "macro_cheat",
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


def label_runs(
    conn: psycopg.Connection,
    *,
    kind: str,
    runs: Sequence[int] | None = None,
    prompt_version: str | None = None,
) -> list[int]:
    """Which label runs to read, for champions or games.

    In order of precedence: explicit `runs` (a pilot or a comparison names the
    runs it means); every run of one `prompt_version` (grading a version, as
    check-anchors does); otherwise the **canonical** runs of that kind
    (label_run.canonical, migration 017) -- the served set. Serving never falls
    through to "whatever ran last": with several regimes sharing a prompt
    version, that is regime mixing by accident.

    Only a database with no canonical runs at all falls back to the old rule,
    the widest-coverage prompt version, so a fresh database still serves.
    """
    table = "champion_label" if kind == "champion" else "game_label"
    with conn.cursor() as cur:
        if runs:
            return list(runs)
        if prompt_version is not None:
            cur.execute(
                f"""select distinct r.id from label_run r join {table} l on l.label_run_id = r.id
                    where r.prompt_version = %s order by r.id""",
                (prompt_version,),
            )
            return [r[0] for r in cur.fetchall()]
        cur.execute(
            f"""select r.id from label_run r
                where r.canonical and exists (select 1 from {table} l where l.label_run_id = r.id)
                order by r.id"""
        )
        canonical = [r[0] for r in cur.fetchall()]
        if canonical:
            return canonical
        cur.execute(
            f"""select r.prompt_version from label_run r join {table} l on l.label_run_id = r.id
                group by r.prompt_version
                order by count(distinct l.{"champion_id, l.role" if kind == "champion" else "game_id"}) desc,
                         max(r.id) desc
                limit 1"""
        )
        row = cur.fetchone()
    return label_runs(conn, kind=kind, prompt_version=row[0]) if row else []


def champion_points(
    conn: psycopg.Connection,
    prompt_version: str | None = None,
    *,
    runs: Sequence[int] | None = None,
) -> list[dict[str, Any]]:
    """Every champion x role as an MMM point, one row each.

    From one set of runs (label_runs: the canonical set unless told otherwise).
    Within the set the latest label per champion x role wins, which is what
    makes a gap-filling run (label_run 10 over 9) union correctly instead of
    double-counting. Each row says which run, prompt, model and effort made it.
    """
    ids = label_runs(conn, kind="champion", runs=runs, prompt_version=prompt_version)
    if not ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            select distinct on (l.champion_id, l.role)
                   l.champion_id, c.name, l.role, l.micro, l.meso, l.macro,
                   r.id, r.prompt_version, r.model, r.effort
            from champion_label l
            join label_run r on r.id = l.label_run_id
            join champion c on c.id = l.champion_id
            where l.label_run_id = any(%s)
            order by l.champion_id, l.role, l.label_run_id desc
            """,
            (ids,),
        )
        return [
            {
                "champion_id": r[0],
                "name": r[1],
                "role": r[2],
                "micro": float(r[3]),
                "meso": float(r[4]),
                "macro": float(r[5]),
                "label_run_id": r[6],
                "prompt_version": r[7],
                "model": r[8],
                "effort": r[9],
            }
            for r in cur.fetchall()
        ]


def game_ids(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("select id from game")
        return {r[0] for r in cur.fetchall()}


def upsert_bank_game(
    conn: psycopg.Connection,
    *,
    game_id: str,
    name: str,
    mode: str | None,
    tier: str,
    parent_id: str | None,
    steam_appid: int | None,
    release_year: int | None,
    bias: str | None = None,
    reach: int | None = None,
    renown: str | None = None,
) -> None:
    """Put one game from the bank files (r3m.bank) into the table.

    The files decide name, mode, tier and parent, and everything they list is
    in the bank: exclusion is a serving decision now, not a bank one. For a row
    that already exists, its Steam id and year win over the file's -- those were
    checked by hand, and a series keeps a null year on purpose
    (009_game_art.sql). is_anchor is never touched: it records where a game's
    validation came from, which an import cannot know.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into game (id, name, mode, tier, parent_id, steam_appid,
                              release_year, bias, reach, renown, is_anchor, in_bank)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false, true)
            on conflict (id) do update set
                name = excluded.name,
                mode = excluded.mode,
                tier = excluded.tier,
                parent_id = excluded.parent_id,
                steam_appid = coalesce(game.steam_appid, excluded.steam_appid),
                release_year = coalesce(game.release_year, excluded.release_year),
                bias = excluded.bias,
                reach = excluded.reach,
                renown = excluded.renown,
                in_bank = true
            """,
            (game_id, name, mode, tier, parent_id, steam_appid, release_year, bias, reach, renown),
        )


def game_labelling_targets(
    conn: psycopg.Connection, game_ids: Sequence[str] | None = None
) -> list[dict[str, Any]]:
    """Games to label. Only the title and mode are returned — deliberately.

    Nothing about category or genre reaches the prompt; passing it would hand
    the labeller the answer the anchors exist to check.
    """
    sql = "select id, name, mode from game"
    params: tuple[Any, ...] = ()
    if game_ids is not None:
        sql += " where id = any(%s)"
        params = (list(game_ids),)
    sql += " order by id"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [{"game_id": r[0], "name": r[1], "mode": r[2]} for r in cur.fetchall()]


_GAME_LABEL_COLUMNS = (
    "micro_precision", "micro_execution", "micro_cheat",
    "meso_deception", "meso_prediction", "meso_exploitation", "meso_cheat",
    "macro_routing", "macro_win_condition", "macro_cheat",
    "micro", "meso", "macro", "rationale",
)


def subtrait_values(
    conn: psycopg.Connection,
    *,
    kind: str,
    column: str,
    prompt_version: str | None = None,
    runs: Sequence[int] | None = None,
) -> dict[Any, float]:
    """One sub-trait for every champion x role or game.

    Same run choice and row choice as champion_points / game_points
    (label_runs, then the latest label per item), so a matcher variant that
    swaps one column in reads exactly the rows the production matcher reads.
    Keys: (champion_id, role) for champions, game_id for games.
    """
    allowed = CHAMPION_LABEL_COLUMNS if kind == "champion" else _GAME_LABEL_COLUMNS
    if column not in allowed or column == "rationale":
        raise ValueError(f"not a {kind} sub-trait: {column}")
    ids = label_runs(conn, kind=kind, runs=runs, prompt_version=prompt_version)
    if kind == "champion":
        query = f"""
            select distinct on (l.champion_id, l.role) l.champion_id, l.role::text, l.{column}
            from champion_label l
            where l.label_run_id = any(%s)
            order by l.champion_id, l.role, l.label_run_id desc
        """
    else:
        query = f"""
            select distinct on (l.game_id) l.game_id, l.{column}
            from game_label l
            where l.label_run_id = any(%s)
            order by l.game_id, l.label_run_id desc
        """
    with conn.cursor() as cur:
        cur.execute(query, (ids,))
        rows = cur.fetchall()
    if kind == "champion":
        return {(r[0], r[1]): float(r[2]) for r in rows if r[2] is not None}
    return {r[0]: float(r[1]) for r in rows if r[1] is not None}


def insert_game_label(
    conn: psycopg.Connection, *, label_run_id: int, game_id: str,
    fields: Mapping[str, Any], raw_response: Mapping[str, Any],
) -> None:
    cols = ", ".join(_GAME_LABEL_COLUMNS)
    marks = ", ".join(["%s"] * len(_GAME_LABEL_COLUMNS))
    with conn.cursor() as cur:
        cur.execute(
            f"""
            insert into game_label (label_run_id, game_id, {cols}, raw_response)
            values (%s, %s, {marks}, %s)
            """,
            (label_run_id, game_id,
             *(fields[c] for c in _GAME_LABEL_COLUMNS), Jsonb(dict(raw_response))),
        )


def game_points(
    conn: psycopg.Connection,
    prompt_version: str | None = None,
    *,
    runs: Sequence[int] | None = None,
) -> list[dict[str, Any]]:
    """Every game as an MMM point, one row each.

    Same rules as champion_points: one set of runs (canonical unless told
    otherwise), latest label per game within it. `bank`, tier and bias are
    carried through for the quiz.
    """
    ids = label_runs(conn, kind="game", runs=runs, prompt_version=prompt_version)
    if not ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            select distinct on (l.game_id)
                   l.game_id, g.name, g.mode, g.in_bank, l.micro, l.meso, l.macro,
                   g.steam_appid, g.release_year, g.bias, g.tier, g.parent_id,
                   r.id, r.prompt_version, r.model, r.effort, g.reach, g.renown
            from game_label l
            join label_run r on r.id = l.label_run_id
            join game g on g.id = l.game_id
            where l.label_run_id = any(%s)
            order by l.game_id, l.label_run_id desc
            """,
            (ids,),
        )
        return [
            {"game_id": r[0], "name": r[1], "mode": r[2], "in_bank": r[3],
             "micro": float(r[4]), "meso": float(r[5]), "macro": float(r[6]),
             "steam_appid": r[7], "release_year": r[8],
             "bias": r[9], "tier": r[10], "parent_id": r[11],
             "label_run_id": r[12], "prompt_version": r[13], "model": r[14], "effort": r[15],
             "reach": r[16], "renown": r[17]}
            for r in cur.fetchall()
        ]

def insert_quiz_session(
    conn: psycopg.Connection,
    *,
    served: list[str],
    loved: list[str],
    disliked: list[str],
    comparisons: list[dict[str, Any]],
    point: list[float],
    dimensions: dict[str, Any],
    champions: list[dict[str, Any]],
    champion_prompt_version: str,
    game_prompt_version: str,
    verdicts: dict[str, str] | None = None,
    reasons: dict[str, str] | None = None,
    events: list[dict[str, Any]] | None = None,
    build: dict[str, Any] | None = None,
    deep_dives: list[dict[str, Any]] | None = None,
) -> int:
    """Store one completed quiz and return its id.

    Called when the result is shown, not when the page loads: an abandoned
    session has nothing to compare against a real account. Verdicts and reasons
    are fixed by then -- sharpening comes after them and changes neither -- so
    update_quiz_session leaves them alone.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into quiz_session (
                served, loved, disliked, comparisons, point, dimensions,
                champions, champion_prompt_version, game_prompt_version,
                verdicts, reasons, events, build, deep_dives
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning id
            """,
            (served, loved, disliked, Jsonb(comparisons), point,
             Jsonb(dimensions), Jsonb(champions),
             champion_prompt_version, game_prompt_version,
             Jsonb(verdicts) if verdicts is not None else None,
             Jsonb(reasons) if reasons is not None else None,
             Jsonb(events) if events is not None else None,
             Jsonb(build) if build is not None else None,
             Jsonb(deep_dives) if deep_dives is not None else None),
        )
        session_id = cur.fetchone()[0]  # type: ignore[index]
    conn.commit()
    return int(session_id)


def update_quiz_session(
    conn: psycopg.Connection,
    *,
    session_id: int,
    loved: list[str],
    disliked: list[str],
    comparisons: list[dict[str, Any]],
    point: list[float],
    dimensions: dict[str, Any],
    champions: list[dict[str, Any]],
    events: list[dict[str, Any]] | None = None,
    served: list[str] | None = None,
    verdicts: dict[str, str] | None = None,
    reasons: dict[str, str] | None = None,
    build: dict[str, Any] | None = None,
    deep_dives: list[dict[str, Any]] | None = None,
) -> bool:
    """Fold a sharpening answer into the session it belongs to -- or resolve a
    session stored without a result (migration 020): the player loved nothing,
    went back, and picked again. Only then may the picks differ; the row
    becomes a result and its events keep the history.

    Every comparison re-posts the result, and each re-post used to insert: one
    tester answering three pairs became four rows, and the panel counted result
    views instead of people. The row now ends holding the final state, and
    `comparisons` still records every step that got it there.

    Matched on the picks as well as the id, so a stale tab or a replayed id
    cannot overwrite a different session -- it gets False and a fresh row.
    Riot id and feedback are untouched: they may already have been attached.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            update quiz_session
               set comparisons = %s, point = %s, dimensions = %s, champions = %s,
                   events = coalesce(%s, events),
                   loved = %s, disliked = %s,
                   served = coalesce(%s, served),
                   verdicts = coalesce(%s, verdicts),
                   reasons = coalesce(%s, reasons),
                   build = coalesce(%s, build),
                   deep_dives = coalesce(%s, deep_dives),
                   outcome = 'result', updated_at = now()
             where id = %s and (outcome <> 'result' or (loved = %s and disliked = %s))
            """,
            (Jsonb(comparisons), point, Jsonb(dimensions), Jsonb(champions),
             Jsonb(events) if events is not None else None,
             loved, disliked, served,
             Jsonb(verdicts) if verdicts is not None else None,
             Jsonb(reasons) if reasons is not None else None,
             Jsonb(build) if build is not None else None,
             Jsonb(deep_dives) if deep_dives is not None else None,
             session_id, loved, disliked),
        )
        updated = cur.rowcount
    conn.commit()
    return updated > 0


def record_progress(
    conn: psycopg.Connection,
    *,
    session_id: int | None,
    step: str,
    served: list[str],
    loved: list[str],
    disliked: list[str],
    verdicts: dict[str, str],
    reasons: dict[str, str],
    events: list[dict[str, Any]],
    deep_dives: list[dict[str, Any]],
    comparisons: list[dict[str, Any]],
    build: dict[str, Any],
    champion_prompt_version: str,
    game_prompt_version: str,
) -> int:
    """Store where a session has got to (migration 022), from its first answer.

    The step is always recorded -- after the result it records the rating --
    but the answers only while the session is still in progress: a result or
    "not enough to go on" is written by its own endpoint and never overwritten
    from here. A missing or unknown id starts a new row.
    """
    if session_id is not None:
        with conn.cursor() as cur:
            cur.execute(
                """
                update quiz_session
                   set last_step = %s, updated_at = now(),
                       served = case when outcome = 'in_progress' then %s else served end,
                       loved = case when outcome = 'in_progress' then %s else loved end,
                       disliked = case when outcome = 'in_progress' then %s else disliked end,
                       verdicts = case when outcome = 'in_progress' then %s else verdicts end,
                       reasons = case when outcome = 'in_progress' then %s else reasons end,
                       -- The log is append-only, so a longer one always
                       -- wins, result or not: "not me" taps come after it.
                       events = case when outcome = 'in_progress'
                                       or jsonb_array_length(%s) >= coalesce(jsonb_array_length(events), 0)
                                     then %s else events end,
                       deep_dives = case when outcome = 'in_progress' then %s else deep_dives end,
                       comparisons = case when outcome = 'in_progress' then %s else comparisons end
                 where id = %s
                """,
                (step, served, loved, disliked, Jsonb(verdicts), Jsonb(reasons), Jsonb(events), Jsonb(events),
                 Jsonb(deep_dives), Jsonb(comparisons), session_id),
            )
            found = cur.rowcount
        conn.commit()
        if found:
            return session_id
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into quiz_session (
                outcome, last_step, served, loved, disliked, comparisons, verdicts, reasons,
                events, deep_dives, build, champion_prompt_version, game_prompt_version
            )
            values ('in_progress', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning id
            """,
            (step, served, loved, disliked, Jsonb(comparisons), Jsonb(verdicts), Jsonb(reasons),
             Jsonb(events), Jsonb(deep_dives), Jsonb(build),
             champion_prompt_version, game_prompt_version),
        )
        new_id = cur.fetchone()[0]  # type: ignore[index]
    conn.commit()
    return int(new_id)


def record_visit(conn: psycopg.Connection, serving: str) -> None:
    """One page load (migration 023). Nothing about the visitor is stored."""
    conn.execute("insert into page_visit (serving) values (%s)", (serving,))
    conn.commit()


# Past this, a session still in progress counts as abandoned in the report.
ABANDONED_AFTER = "1 hour"


def session_dropoff(conn: psycopg.Connection, serving: str) -> dict[str, Any]:
    """Where sessions on one serving mode stop (migration 022): how many
    started, how many reached each ending, and for the abandoned the last step
    reached. Separate from the headline, which counts completed sessions only."""
    rows = conn.execute(
        f"""
        select outcome, coalesce(last_step, '-'), feels_right is not null,
               outcome = 'in_progress' and updated_at < now() - interval '{ABANDONED_AFTER}'
        from quiz_session
        where build ->> 'serving' = %s
        """,
        (serving,),
    ).fetchall()
    visits = (conn.execute("select count(*) from page_visit where serving = %s", (serving,)).fetchone()[0]
              if has_table(conn, "page_visit") else None)
    out: dict[str, Any] = {"visits": visits, "started": len(rows), "outcomes": {},
                           "abandoned_at": {}, "still_going": 0, "rated": 0}
    for outcome, step, rated, abandoned in rows:
        out["outcomes"][outcome] = out["outcomes"].get(outcome, 0) + 1
        if outcome == "in_progress":
            if abandoned:
                out["abandoned_at"][step] = out["abandoned_at"].get(step, 0) + 1
            else:
                out["still_going"] += 1
        out["rated"] += bool(rated)
    return out


def insert_unresolved_session(
    conn: psycopg.Connection,
    *,
    outcome: str,
    served: list[str],
    loved: list[str],
    disliked: list[str],
    verdicts: dict[str, str],
    reasons: dict[str, str],
    events: list[dict[str, Any]],
    build: dict[str, Any],
    champion_prompt_version: str,
    game_prompt_version: str,
) -> int:
    """Store a session that ended without a result (migration 020): no point,
    no champions, only what was shown and said, and how it ended."""
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into quiz_session (
                outcome, served, loved, disliked, comparisons, verdicts, reasons,
                events, build, champion_prompt_version, game_prompt_version
            )
            values (%s, %s, %s, %s, '[]', %s, %s, %s, %s, %s, %s)
            returning id
            """,
            (outcome, served, loved, disliked, Jsonb(verdicts), Jsonb(reasons),
             Jsonb(events), Jsonb(build), champion_prompt_version, game_prompt_version),
        )
        session_id = cur.fetchone()[0]  # type: ignore[index]
    conn.commit()
    return int(session_id)


def update_unresolved_session(
    conn: psycopg.Connection,
    *,
    session_id: int,
    outcome: str,
    served: list[str],
    loved: list[str],
    disliked: list[str],
    verdicts: dict[str, str],
    reasons: dict[str, str],
    events: list[dict[str, Any]],
) -> bool:
    """The same player ending without a result again. Never touches a session
    that has a result: False, and the caller stores a fresh row."""
    with conn.cursor() as cur:
        cur.execute(
            """
            update quiz_session
               set outcome = %s, served = %s, loved = %s, disliked = %s,
                   verdicts = %s, reasons = %s, events = %s, updated_at = now()
             where id = %s and point is null
            """,
            (outcome, served, loved, disliked, Jsonb(verdicts), Jsonb(reasons),
             Jsonb(events), session_id),
        )
        updated = cur.rowcount
    conn.commit()
    return updated > 0


def session_outcomes(conn: psycopg.Connection) -> dict[str, dict[str, Any]]:
    """How sessions ended, per panel round: round 1 predates the build column
    (migration 019), round 2 carries it, split by serving mode. For the panel report, beside unread
    dimensions -- a player the quiz could not read at all is its most common
    predicted failure, and absent from the Riot-id comparison by construction."""
    rows = conn.execute(
        """
        -- Round 2 split by serving mode: the short-lived 28-card build
        -- (panel-round-1) is kept apart from the upgraded one (panel-round-2).
        select case when build is null then 'round 1'
                    else 'round 2, ' || coalesce(build ->> 'serving', '?') end,
               outcome,
               riot_id is not null,
               (select count(*) from jsonb_each(coalesce(dimensions, '{}'::jsonb)) d
                 where not coalesce((d.value ->> 'read')::boolean, false)),
               coalesce(events, '[]'::jsonb) @> '[{"type": "outcome"}]'
        from quiz_session
        """
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for rnd, outcome, riot, unread, had_none in rows:
        r = out.setdefault(rnd, {"sessions": 0, "riot_id": 0, "outcomes": {}, "unread": {},
                                 "recovered": 0})
        r["sessions"] += 1
        r["riot_id"] += bool(riot)
        r["outcomes"][outcome] = r["outcomes"].get(outcome, 0) + 1
        if outcome == "result":
            r["unread"][int(unread)] = r["unread"].get(int(unread), 0) + 1
            r["recovered"] += bool(had_none)
    return out


def attach_panel_details(
    conn: psycopg.Connection,
    *,
    session_id: int,
    riot_id: str | None,
    feedback: str | None,
    feels_right: str | None = None,
) -> bool:
    """Add a Riot id and/or free text to a session already stored.

    Separate from the insert because it is asked for separately: the result
    comes first, then the request to check it against a real account, so
    somebody can see what they are being asked about before answering.
    Returns False when the id does not exist rather than raising -- a stale tab
    posting to a wiped database is not an error worth showing a tester.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            update quiz_session
               set riot_id = coalesce(%s, riot_id),
                   feedback = coalesce(%s, feedback),
                   feels_right = coalesce(%s, feels_right)
             where id = %s
            """,
            (riot_id or None, feedback or None, feels_right or None, session_id),
        )
        updated = cur.rowcount
    conn.commit()
    return updated > 0


def champion_popularity(conn: psycopg.Connection) -> dict[str, int]:
    """Games per champion in the match sample -- the panel's popularity baseline
    ("recommend what is most played"). Empty where no sample was loaded."""
    rows = conn.execute(
        """
        select c.id, count(*)
        from match_participant p
        join champion c on c.riot_key = p.champion_key
        group by c.id
        """
    ).fetchall()
    return {champion: n for champion, n in rows}


# Sessions kept in the data but never in the headline: the builder's own test
# runs, whose answers were given by someone who knows what the quiz measures.
# #28: Sergi's first run of the upgraded build, 2026-09-30, with his Riot id.
EXCLUDED_FROM_HEADLINE = (28,)


def reading_feedback(conn: psycopg.Connection, serving: str) -> dict[str, dict[str, int]]:
    """Per sentence id: in how many sessions it was shown, and in how many it
    was marked "not me" (last state of the toggle). From the event log."""
    rows = conn.execute(
        """
        select id, events from quiz_session
        where build ->> 'serving' = %s and events is not null
        """,
        (serving,),
    ).fetchall()
    out: dict[str, dict[str, int]] = {}
    for _, events in rows:
        shown: set[str] = set()
        rejected: dict[str, bool] = {}
        for e in events:
            if e.get("type") == "reading_shown":
                shown.update(e.get("sentences", []))
            elif e.get("type") == "not_me":
                rejected[e.get("sentence")] = bool(e.get("on"))
        for sid in shown:
            s = out.setdefault(sid, {"shown": 0, "not_me": 0})
            s["shown"] += 1
            s["not_me"] += bool(rejected.get(sid))
    return out


def panel_sessions_to_check(
    conn: psycopg.Connection, *, include_checked: bool = False
) -> list[dict[str, Any]]:
    """Sessions that named an account, not yet compared unless asked for all.

    Carries the picks as well as the stored point, so the comparison pass can
    recompute the point under a different matcher and compare like with like.
    """
    with conn.cursor() as cur:
        cur.execute(
            f"""
            select id, riot_id, point, dimensions, loved, disliked, comparisons, champions,
                   -- read through to_jsonb so this works before migration 015
                   -- adds the column: absent reads as null, not an error
                   to_jsonb(quiz_session) -> 'actual_mains'
            from quiz_session
            where riot_id is not null and point is not null and outcome = 'result'
              -- Round 2 sessions on the 28-card build stay in the data but out of
              -- the headline (Sergi, 2026-09-30): only round 1 and panel-round-2.
              and coalesce(to_jsonb(quiz_session) -> 'build' ->> 'serving', '') <> 'panel-round-1'
              and id <> all(%s)
                  {"" if include_checked else "and checked_at is null"}
            order by created_at
            """,
            (list(EXCLUDED_FROM_HEADLINE),),
        )
        return [
            {"id": r[0], "riot_id": r[1],
             "point": [float(x) for x in r[2]], "dimensions": r[3],
             "loved": list(r[4]), "disliked": list(r[5]),
             "comparisons": r[6] or [], "champions": r[7] or [],
             "actual_mains": r[8] or None}
            for r in cur.fetchall()
        ]


def record_panel_check(
    conn: psycopg.Connection,
    *,
    session_id: int,
    actual_point: list[float] | None,
    actual_games: int,
    actual_mains: list[dict[str, Any]],
) -> None:
    """Store what this person actually plays, and its centroid."""
    with conn.cursor() as cur:
        cur.execute(
            """
            update quiz_session
               set checked_at = now(), actual_point = %s, actual_games = %s,
                   actual_mains = %s
             where id = %s
            """,
            (actual_point, actual_games, Jsonb(actual_mains), session_id),
        )
    conn.commit()


def riot_key(riot_id: str) -> str:
    """A Riot id normalised for joining (migration 024): lowercased, no
    whitespace -- testers type "JohnRod #warud" and "johnrod#warud" alike."""
    return "".join(riot_id.split()).lower()


def insert_riot_mains(
    conn: psycopg.Connection,
    *,
    riot_id: str,
    resolved: str | None,
    tag_guessed: bool,
    fetched_at: str,
    mains: list[tuple[str, str, int]],
    source: str,
) -> bool:
    """Record one fetch of an account's mains. Append-only: a refetch is a new
    row; the same fetch twice (same account, same time) is skipped. True if a
    row was added."""
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into riot_mains (riot_id, riot_key, resolved, resolved_key, tag_guessed,
                                    fetched_at, games, mains, source)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (riot_key, fetched_at) do nothing
            """,
            (riot_id, riot_key(riot_id), resolved, riot_key(resolved) if resolved else None,
             tag_guessed, fetched_at, sum(g for *_, g in mains),
             Jsonb([{"champion_id": c, "role": r, "games": g} for c, r, g in mains]), source),
        )
        added = cur.rowcount
    conn.commit()
    return added > 0


def latest_riot_mains(conn: psycopg.Connection, riot_id: str) -> dict[str, Any] | None:
    """The most recent fetch for this account, matched on the id as typed or
    as resolved; None if it was never fetched."""
    key = riot_key(riot_id)
    row = conn.execute(
        """
        select riot_id, resolved, tag_guessed, fetched_at, mains from riot_mains
        where riot_key = %s or resolved_key = %s
        order by fetched_at desc limit 1
        """,
        (key, key),
    ).fetchone()
    if row is None:
        return None
    return {"riot_id": row[0], "resolved": row[1], "tag_guessed": row[2],
            "fetched_at": row[3].isoformat(timespec="seconds"),
            "mains": [(m["champion_id"], m["role"], m["games"]) for m in row[4]]}


def has_column(conn: psycopg.Connection, table: str, column: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            select 1 from information_schema.columns
             where table_schema = 'public' and table_name = %s and column_name = %s
            """,
            (table, column),
        )
        return cur.fetchone() is not None


def has_table(conn: psycopg.Connection, table: str) -> bool:
    return conn.execute("select to_regclass(%s) is not null", (f"public.{table}",)).fetchone()[0]


def canonical_runs(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """The served label runs (migration 017), with what made them."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select r.id, r.prompt_version, r.model, r.effort, r.started_at::date,
                   (select count(*) from champion_label l where l.label_run_id = r.id),
                   (select count(*) from game_label g where g.label_run_id = r.id)
            from label_run r where r.canonical order by r.id
            """
        )
        return [
            {"id": r[0], "prompt_version": r[1], "model": r[2], "effort": r[3], "date": r[4],
             "kind": "champion" if r[5] else "game", "rows": r[5] or r[6]}
            for r in cur.fetchall()
        ]


def set_canonical(conn: psycopg.Connection, *, kind: str, ids: Sequence[int]) -> None:
    """Replace the served runs of one kind. Checks belong to the caller
    (r3m canonical), which refuses a set that mixes regimes."""
    table = "champion_label" if kind == "champion" else "game_label"
    with conn.cursor() as cur:
        cur.execute(
            f"select r.id from label_run r where r.id = any(%s) "
            f"and exists (select 1 from {table} l where l.label_run_id = r.id)",
            (list(ids),),
        )
        found = {r[0] for r in cur.fetchall()}
        missing = sorted(set(ids) - found)
        if missing:
            raise ValueError(f"no {kind} labels in label_run {missing}")
        cur.execute(
            f"update label_run r set canonical = false "
            f"where exists (select 1 from {table} l where l.label_run_id = r.id)"
        )
        cur.execute("update label_run set canonical = true where id = any(%s)", (list(ids),))
    conn.commit()
