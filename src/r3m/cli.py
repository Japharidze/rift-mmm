"""Command line entry point."""

import argparse
import sys
import time
from pathlib import Path

import httpx

from r3m import anchors, db, dump as dump_mod, fetch, ingest, quiz as quiz_mod, sample, scoring
from r3m.labeling import games as labeling_games
from r3m.labeling import run as labeling_run
from r3m.migrate import apply_migrations
from r3m.riot_api import RiotApi


def _migrate(args: argparse.Namespace) -> int:
    with db.connect() as conn:
        applied = apply_migrations(conn)
    print(f"applied: {', '.join(applied)}" if applied else "schema already up to date")
    return 0


def _ingest(args: argparse.Namespace) -> int:
    # ~170 requests with nothing to show for ten seconds otherwise.
    print("fetching champions from Data Dragon ...", flush=True)
    result = ingest.run(args.version)
    print(f"ingested {result.champions} champions from patch {result.version}")
    return 0


def _sample(args: argparse.Namespace) -> int:
    api = RiotApi(platform=args.platform)

    with db.connect() as conn:
        existing = db.count_matches(conn)
    if existing >= args.matches:
        print(
            f"{existing} matches already stored, at or above the target of "
            f"{args.matches} - nothing to do"
        )
        return 0

    started = time.monotonic()

    def progress(total: int, target: int) -> None:
        if total % 25:
            return
        elapsed = time.monotonic() - started
        added = total - existing
        rate = added / elapsed * 60 if elapsed else 0
        remaining = (target - total) / rate if rate else 0
        print(
            f"  {total}/{target} matches  (+{added} this run, "
            f"{rate:.0f}/min, ~{remaining:.0f} min left)",
            flush=True,
        )

    print(
        f"sampling ranked solo on {args.platform}: "
        f"{existing} stored, target {args.matches}, {args.matches - existing} to go ..."
    )
    try:
        result = sample.run(api, target=args.matches, progress=progress)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in (401, 403):
            raise
        # Development keys last 24 hours, so this is the expected failure, not
        # an exceptional one. Whatever was crawled before it is already stored.
        print(
            "Riot rejected the API key (HTTP "
            f"{exc.response.status_code}). Development keys expire every 24 "
            "hours - regenerate at developer.riotgames.com and update "
            "RIOT_API_KEY in .env. Matches already stored are kept; re-running "
            "resumes from there."
        )
        return 1
    print(
        f"stored {result.stored} new matches "
        f"({result.total} total, {result.requests} API calls)"
    )
    if result.stored:
        _autodump()
    return 0


def _label(args: argparse.Namespace) -> int:
    champions = args.champions.split(",") if args.champions else None
    print(
        f"labelling {'all live champion x role rows' if champions is None else champions} "
        f"with {args.model} ...",
        flush=True,
    )
    result = labeling_run.run(model=args.model, champions=champions, note=args.note)
    if result.targeted == 0:
        print(
            "nothing to label: champion_role_live has no rows in scope. "
            "It is built from match_participant, so run `r3m sample` "
            "first (or check --champions against champion ids that exist)."
        )
        return 1
    if result.label_run_id is None:
        print(
            f"nothing labelled: all {result.targeted} failed, so no run was recorded"
        )
    else:
        print(
            f"label_run {result.label_run_id}: {result.labelled}/{result.targeted} "
            f"labelled, {len(result.failed)} failed"
        )
    for failure in result.failed:
        print(f"  FAILED {failure.champion_id} ({failure.role}): {failure.error}")
    if result.labelled:
        _autodump()
    return 1 if result.failed else 0


def _check_anchors(args: argparse.Namespace) -> int:
    result = anchors.check(prompt_version=args.prompt_version)
    print(f"prompt {result.prompt_version}  ({result.rows} champion x role rows)\n")

    current = None
    for c in result.comparisons:
        if c.champion_id != current:
            current = c.champion_id
            print(f"{c.champion_id}")
        mark = "pass" if c.inside else ("FAIL" if c.blocking else "miss")
        drift = "" if c.inside else f"  {c.drift:+.2f}"
        print(
            f"  {c.dimension:6} {c.label:.2f}  [{c.low:.2f}-{c.high:.2f}]  "
            f"{c.tier:12} {mark}{drift}"
        )

    print(
        f"\n{len(result.comparisons)} scores checked, "
        f"{len(result.failures)} blocking failures, "
        f"{len(result.misses)} non-blocking misses"
    )
    if result.unlabelled:
        print(f"not covered by this run: {', '.join(result.unlabelled)}")
    # Non-zero on a blocking failure: this is a regression test, so it has to be
    # usable as one from a script.
    return 1 if result.failures else 0


def _roles(args: argparse.Namespace) -> int:
    with db.connect() as conn, conn.transaction():
        written = db.replace_match_data_roles(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                select count(*), count(*) filter (where is_primary),
                       count(distinct champion_id)
                from champion_role where source = 'match_data'
                """
            )
            total, primary, champions = cur.fetchone()  # type: ignore[misc]
    if written == 0:
        print(
            "champion_role_live is empty, so nothing was written. It is built "
            "from match_participant - run `r3m sample` first."
        )
        return 1
    print(
        f"champion_role: {total} rows across {champions} champions "
        f"({primary} primary, {total - primary} secondary)"
    )
    _autodump()
    return 0


def _match(args: argparse.Namespace) -> int:
    point = (args.micro, args.meso, args.macro)
    if not all(0.0 <= x <= 1.0 for x in point):
        print("each coordinate must be between 0 and 1")
        return 1

    results = scoring.neighbourhood(point, n=args.n)
    if not results:
        print("no labels to match against - run `r3m label` first")
        return 1

    print(f"micro {point[0]:.2f}  meso {point[1]:.2f}  macro {point[2]:.2f}\n")
    for m in results:
        print(
            f"  {m.name:16} {m.role:8} "
            f"({m.point[0]:.2f} {m.point[1]:.2f} {m.point[2]:.2f})  "
            f"d={m.distance:.3f}  {m.confidence}"
        )
    lanes = {m.role for m in results}
    if len(lanes) == 1:
        print(f"\n  all {len(results)} sit in one lane ({lanes.pop()})")
    return 0


def _label_games(args: argparse.Namespace) -> int:
    games = args.games.split(",") if args.games else None
    print(f"labelling {'all games' if games is None else games} with {args.model} ...",
          flush=True)
    try:
        result = labeling_games.run(model=args.model, games=games, note=args.note)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in (401, 403):
            raise
        print("Anthropic rejected the API key - check ANTHROPIC_API_KEY in .env")
        return 1
    if result.targeted == 0:
        print("nothing to label: the game table is empty")
        return 1
    if result.label_run_id is None:
        print(f"nothing labelled: all {result.targeted} failed, so no run was recorded")
    else:
        print(f"label_run {result.label_run_id}: {result.labelled}/{result.targeted} "
              f"labelled, {len(result.failed)} failed")
    for failure in result.failed:
        print(f"  FAILED {failure.champion_id}: {failure.error}")
    if result.labelled:
        _autodump()
    return 1 if result.failed else 0


def _dump(args: argparse.Namespace) -> int:
    counts = dump_mod.row_counts()
    try:
        path = dump_mod.dump(force=args.force)
    except RuntimeError as exc:
        print(exc)
        return 1
    size = path.stat().st_size / 1_000_000
    print(f"wrote {path.relative_to(dump_mod.ROOT)}  ({size:.1f} MB)")
    for table, n in counts.items():
        print(f"  {table:20}{n:>8}")
    return 0


def _restore(args: argparse.Namespace) -> int:
    path = Path(args.file) if args.file else dump_mod.latest()
    if path is None:
        print("no dump found in dumps/")
        return 1
    try:
        dump_mod.restore(path)
    except RuntimeError as exc:
        print(exc)
        return 1
    print(f"restored {path.name}")
    for table, n in dump_mod.row_counts().items():
        print(f"  {table:20}{n:>8}")
    return 0


def _autodump() -> None:
    """Refresh the dump after a run that cost real money or time.

    Best effort, and deliberately incapable of failing the caller: a 45-minute
    crawl or a $4 labelling pass must not exit non-zero because pg_dump is
    missing on this machine. Worst case you get a warning and run `r3m dump`
    yourself.

    It writes the file but does not commit it. A dump sitting next to the
    database protects against a dropped volume, not against changing machines —
    that needs it pushed, and committing on someone's behalf is a step too far.
    """
    try:
        path = dump_mod.dump()
    except Exception as exc:  # noqa: BLE001 - a backup must never fail the run
        print(f"  (could not refresh the dump: {exc}; run `r3m dump` when you can)")
        return
    print(f"  dump refreshed: {path.relative_to(dump_mod.ROOT)} — commit it to keep it")


def _quiz(args: argparse.Namespace) -> int:
    with db.connect() as conn:
        rows = db.game_points(conn)
    if not rows:
        print("no games labelled yet - run `r3m label-games` first")
        return 1

    if args.list:
        for r in sorted(rows, key=lambda r: r["game_id"]):
            print(f"  {r['game_id']:22}{r['name'][:28]:30}"
                  f"{r['micro']:.2f} {r['meso']:.2f} {r['macro']:.2f}")
        return 0

    seen: list[str] = []
    if args.interactive:
        served: list[str] = []
        loved: list[str] = []
        disliked: list[str] = []
        print("l = loved it,  d = played it but it did not stick,  "
              "anything else = never played\n")
        while (item := quiz_mod.next_item(served, loved, disliked, rows)) is not None:
            label = item["name"] + (f" ({item['mode']})" if item["mode"] else "")
            answer = input(f"  {len(served) + 1}. {label}? ").strip().lower()
            served.append(item["game_id"])
            if answer.startswith("l"):
                loved.append(item["game_id"])
            elif answer.startswith("d"):
                disliked.append(item["game_id"])
        if not loved:
            print("\nnothing you enjoyed, so there is no positive signal to go on.")
            return 1
        args.games = ",".join(loved)
        args.dislikes = ",".join(disliked)
        seen = served
        print(f"\nasked {len(served)}: {len(loved)} loved, {len(disliked)} bounced off")

    if not args.games:
        print("pass --games with comma-separated ids, --interactive, or --list")
        return 1

    try:
        est = quiz_mod.estimate(
            args.games.split(","),
            args.dislikes.split(",") if args.dislikes else [],
            rows=rows,
        )
    except ValueError as exc:
        print(exc)
        return 1

    for g in est.unknown:
        print(f"  unknown game, ignored: {g}")
    print("\nyou enjoyed")
    for g in est.loved:
        print(f"  {g['name'][:26]:28}{g['micro']:.2f} {g['meso']:.2f} {g['macro']:.2f}")

    print("\nyour profile")
    for d in quiz_mod.DIMENSIONS:
        dim = est.dimensions[d]
        mark = f"{dim.informative} clear pick(s)" if dim.read else "NOT READ"
        print(f"  {d:6} {dim.value:.2f}   {mark}")

    matches = quiz_mod.champions_for(est, n=args.n)
    print("\nclosest champions")
    for m in matches:
        print(f"  {m.name:16}{m.role:8} d={m.distance:.2f}  {m.confidence}")
    if all(m.confidence == "distant" for m in matches):
        print(
            "\n  Nothing lands close. League champions all carry some of all "
            "three\n  demands, so a taste at the edges of the space has no real "
            "neighbour -\n  treat these as the nearest thing, not as a fit."
        )

    # The frozen decision: report an unread dimension, never impute it, and
    # make the gap a retry hook rather than an apology.
    for d in est.unread:
        # everything already shown, not only what was picked
        shown = seen or est.answered
        more = quiz_mod.suggest_for(d, exclude=shown, rows=rows, n=4)
        print(f"\n  we could not read your {d}. Played any of these?")
        print("    " + ", ".join(f"{g['name']}" for g in more))
    return 0


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    # api/ is not part of the installed package — it imports r3m, not the other
    # way round, so the HTTP layer stays something you could delete.
    sys.path.insert(0, str(dump_mod.ROOT / "api"))
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="r3m")
    sub = parser.add_subparsers(dest="command", required=True)

    migrate = sub.add_parser("migrate", help="apply pending schema migrations")
    migrate.set_defaults(func=_migrate)

    ingest_cmd = sub.add_parser("ingest", help="load a Data Dragon patch into the database")
    ingest_cmd.add_argument(
        "--version", help="patch to ingest, e.g. 16.18.1 (default: latest published)"
    )
    ingest_cmd.set_defaults(func=_ingest)

    sample_cmd = sub.add_parser(
        "sample", help="crawl ranked solo matches for the role distribution"
    )
    sample_cmd.add_argument(
        "--matches", type=int, default=2000,
        help="total matches to hold in the database, not the number to add (default: 2000)",
    )
    sample_cmd.add_argument("--platform", default="euw1", help="e.g. euw1, na1, kr")
    sample_cmd.set_defaults(func=_sample)

    label_cmd = sub.add_parser("label", help="label champion x role rows with the MMM sub-traits")
    label_cmd.add_argument(
        "--model", default=labeling_run.DEFAULT_MODEL,
        help=f"Anthropic model id (default: {labeling_run.DEFAULT_MODEL})",
    )
    label_cmd.add_argument(
        "--champions", help="comma-separated champion ids to label (default: every live role)"
    )
    label_cmd.add_argument("--note", help="free text stored on the label_run row")
    label_cmd.set_defaults(func=_label)

    label_games_cmd = sub.add_parser(
        "label-games", help="label games with the MMM sub-traits"
    )
    label_games_cmd.add_argument("--model", default=labeling_run.DEFAULT_MODEL)
    label_games_cmd.add_argument(
        "--games", help="comma-separated game ids (default: every game in the table)"
    )
    label_games_cmd.add_argument("--note", help="what changed since the last run")
    label_games_cmd.set_defaults(func=_label_games)

    quiz_cmd = sub.add_parser(
        "quiz", help="games you have played -> an MMM point -> champions"
    )
    quiz_cmd.add_argument("--games", help="comma-separated ids of games you enjoyed")
    quiz_cmd.add_argument("--dislikes", default="",
                          help="comma-separated ids you played but bounced off")
    quiz_cmd.add_argument("--list", action="store_true", help="show the bank")
    quiz_cmd.add_argument("--interactive", action="store_true",
                          help="be asked, one game at a time")
    quiz_cmd.add_argument("-n", type=int, default=5)
    quiz_cmd.set_defaults(func=_quiz)

    serve_cmd = sub.add_parser("serve", help="run the HTTP API for the frontend")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=8000)
    serve_cmd.add_argument("--reload", action="store_true")
    serve_cmd.set_defaults(func=_serve)

    dump_cmd = sub.add_parser("dump", help="write a data-only dump to dumps/")
    dump_cmd.add_argument("--force", action="store_true",
                          help="overwrite even if the existing dump is larger")
    dump_cmd.set_defaults(func=_dump)

    restore_cmd = sub.add_parser(
        "restore", help="load a dump into an empty, already-migrated database"
    )
    restore_cmd.add_argument("--file", help="dump to load (default: newest in dumps/)")
    restore_cmd.set_defaults(func=_restore)

    check_cmd = sub.add_parser(
        "check-anchors", help="compare a labelling run against anchors/champions.yaml"
    )
    check_cmd.add_argument(
        "--prompt-version", default=None,
        help="which prompt version's labels to grade (default: widest coverage)",
    )
    check_cmd.set_defaults(func=_check_anchors)

    roles_cmd = sub.add_parser(
        "roles", help="write champion_role from the match sample"
    )
    roles_cmd.set_defaults(func=_roles)

    match_cmd = sub.add_parser(
        "match", help="champions nearest an MMM point"
    )
    match_cmd.add_argument("micro", type=float)
    match_cmd.add_argument("meso", type=float)
    match_cmd.add_argument("macro", type=float)
    match_cmd.add_argument("-n", type=int, default=5, help="how many (default: 5)")
    match_cmd.set_defaults(func=_match)

    args = parser.parse_args()
    try:
        return args.func(args)
    finally:
        fetch.close()
