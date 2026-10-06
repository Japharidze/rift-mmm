"""Command line entry point."""

import argparse
import sys
import time
from pathlib import Path

import httpx

from r3m import anchors, bank, db, dump as dump_mod, fetch, ingest, panel, quiz as quiz_mod, sample, scoring, transfer
from r3m.labeling import games as labeling_games
from r3m.labeling import run as labeling_run
from r3m.migrate import apply_migrations
from r3m.riot_api import RiotApi

# output_config.effort values on the current Opus models.
EFFORTS = ("low", "medium", "high", "xhigh", "max")


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
        f"with {args.model} at effort {args.effort}, prompt {args.prompt_version} ...",
        flush=True,
    )
    result = labeling_run.run(
        model=args.model, effort=args.effort, champions=champions, note=args.note,
        prompt_version=args.prompt_version,
    )
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
    u = result.usage
    cost = u.dollars(args.model)
    print(f"usage: {u.calls} calls, input {u.input:,} + cache write {u.cache_write:,} + "
          f"cache read {u.cache_read:,}, output {u.output:,} tokens"
          + (f" ~ ${cost:.2f} at list price" if cost is not None else ""))
    print(f"retries: {u.no_tool} replies without the tool call, {u.invalid} invalid calls")
    if result.labelled:
        _autodump()
    return 1 if result.failed else 0


def _place(args: argparse.Namespace) -> int:
    from r3m import place

    if args.restore:
        return place.restore()
    return place.run(purists_only=args.purists, role=args.role, review=args.review)


def _check_anchors(args: argparse.Namespace) -> int:
    runs = [int(x) for x in args.runs.split(",")] if args.runs else None
    result = anchors.check(prompt_version=args.prompt_version, runs=runs)
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
    print(f"labelling {'all games' if games is None else games} with {args.model} "
          f"at effort {args.effort} ...", flush=True)
    try:
        result = labeling_games.run(
            model=args.model, effort=args.effort, games=games, note=args.note
        )
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
    u = result.usage
    cost = u.dollars(args.model)
    print(f"usage: {u.calls} calls, input {u.input:,} + cache write {u.cache_write:,} + "
          f"cache read {u.cache_read:,}, output {u.output:,} tokens"
          + (f" ~ ${cost:.2f} at list price" if cost is not None else ""))
    print(f"retries: {u.no_tool} replies without the tool call, {u.invalid} invalid calls")
    if result.labelled:
        _autodump()
    return 1 if result.failed else 0


def _labels_export(args: argparse.Namespace) -> int:
    ids = [int(x) for x in args.runs.split(",")]
    with db.connect() as conn:
        data = transfer.export_runs(conn, ids)
    out = Path(args.out)
    transfer.write(data, out)
    for e in data["runs"]:
        r = e["run"]
        print(f"label_run {r['id']:>3}  {e['kind']:8} {r['prompt_version']:9} {r['model']} "
              f"effort {r['effort'] or 'default'}  {len(e['labels'])} labels")
    print(f"wrote {out}")
    return 0


def _labels_import(args: argparse.Namespace) -> int:
    data = transfer.read(Path(args.file))
    with db.connect() as conn:
        report = transfer.import_runs(conn, data)
    for r in report:
        print(f"source run {r['source']:>3} -> label_run {r['target']:>3}  {r['kind']:8} "
              f"{r['rows']} labels  {r['status']}")
    print("\nnothing is served until you run `r3m canonical` with the ids above")
    return 0


def _canonical(args: argparse.Namespace) -> int:
    """Show or change the served label runs, refusing a mixed regime."""
    with db.connect() as conn:
        before = db.canonical_runs(conn)
        changes = {k: [int(x) for x in v.split(",")] for k, v in
                   (("champion", args.champion_runs), ("game", args.game_runs)) if v}
        if changes:
            # What the set would be after the change, checked before writing.
            with conn.cursor() as cur:
                cur.execute("select id, prompt_version, model, effort from label_run where id = any(%s)",
                            ([i for ids in changes.values() for i in ids],))
                proposed = {r[0]: r[1:] for r in cur.fetchall()}
            after = [(r["id"], r["kind"], r["prompt_version"], r["model"], r["effort"])
                     for r in before if r["kind"] not in changes]
            after += [(i, k, *proposed.get(i, (None, None, None)))
                      for k, ids in changes.items() for i in ids]
            regimes = {(m, e) for _, _, _, m, e in after}
            if len(regimes) > 1:
                print("refused: the served set would mix models or effort levels -- "
                      + "; ".join(f"{m} effort {e or 'default'}" for m, e in sorted(regimes, key=str))
                      + ". Champions and games must share one labelling regime (CLAUDE.md).")
                return 1
            for kind in ("champion", "game"):
                versions = {p for _, k, p, _, _ in after if k == kind}
                if len(versions) > 1:
                    print(f"refused: {kind} runs would mix prompt versions {sorted(versions)}")
                    return 1
            for kind, ids in changes.items():
                db.set_canonical(conn, kind=kind, ids=ids)
        for r in db.canonical_runs(conn):
            print(f"{r['kind']:8} label_run {r['id']:>3}  {r['prompt_version']:9} {r['model']}  "
                  f"effort {r['effort'] or 'default'}  {r['rows']} rows  ({r['date']})")
    return 0


def _bank_candidates(args: argparse.Namespace) -> int:
    p = bank.candidates(Path(args.csv))
    print(f"wrote {bank.STEAM_FILE.relative_to(bank.ROOT)}: {len(p.selected)} selected, "
          f"{len(p.reserve)} in reserve")
    print("dropped: " + ", ".join(f"{why} {n}" for why, n in p.dropped.most_common()))
    print("per genre: " + ", ".join(f"{g} {n}" for g, n in p.genre_counts.most_common()))
    if p.capped:
        print(f"held back by the cap of {bank.GENRE_CAP}: "
              + ", ".join(f"{g} {n}" for g, n in p.capped.most_common()))
    return 0


def _bank_import(args: argparse.Namespace) -> int:
    with db.connect() as conn:
        r = bank.import_bank(conn)
    print(f"bank: {r.deck} deck, {r.deep} deep ({r.inserted} new, {r.updated} updated)")
    if r.untracked:
        print(f"in the game table but in no bank file: {', '.join(r.untracked)}")
    return 0


def _panel_check(args: argparse.Namespace) -> int:
    with db.connect() as conn:
        if args.write and not db.has_column(conn, "quiz_session", "actual_mains"):
            # Checked before any Riot call, so a refused write costs nothing.
            print("--write needs migration 015 (quiz_session.actual_mains) on this database. "
                  "Nothing fetched, nothing written.")
            return 1
        sessions = db.panel_sessions_to_check(conn, include_checked=args.all)
        outcomes = (db.session_outcomes(conn)
                    if db.has_column(conn, "quiz_session", "outcome") else None)
        dropoff = ({"panel-round-2": db.session_dropoff(conn, "panel-round-2")}
                   if db.has_column(conn, "quiz_session", "last_step") else None)
        feedback = (db.reading_feedback(conn, "panel-round-2")
                    if db.has_column(conn, "quiz_session", "events") else None)
        if not sessions:
            # Completion and drop-off still matter with no Riot id to check.
            print("no sessions with a Riot id to check\n")
            print(panel.report([], outcomes, dropoff, feedback))
            return 0
        variant_list = panel.variants(conn)
        popularity = db.champion_popularity(conn)
        cache = panel.load_cache()
        api = RiotApi(platform=panel.PLATFORM)
        # The same account fetched for another session is reused, not refetched.
        known = ((lambda rid: db.latest_riot_mains(conn, rid))
                 if db.has_table(conn, "riot_mains") else None)
        checks = []
        try:
            for s in sessions:
                print(f"checking #{s['id']} ...", flush=True)
                checks.append(panel.check_session(api, s, variant_list, cache=cache,
                                                  refetch=args.refetch, popularity=popularity,
                                                  known=known))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                print("Riot rejected the key: development keys expire every 24 hours. "
                      "Fetch a new one at developer.riotgames.com into RIOT_API_KEY.")
                return 1
            raise
        finally:
            panel.save_cache(cache)  # whatever was fetched survives a failure mid-run
        print()
        print(panel.report(checks, outcomes, dropoff, feedback))
        if args.write:
            written = 0
            for c in checks:
                current = c.by_variant.get("current")
                if c.error or current is None or not c.mains:
                    continue
                point = current.actual_point
                db.record_panel_check(
                    conn, session_id=c.session_id,
                    actual_point=[round(x, 2) for x in point] if point else None,
                    actual_games=c.placed_games,
                    actual_mains=[{"champion_id": ch, "role": r, "games": g}
                                  for ch, r, g in c.mains],
                )
                written += 1
            recorded = 0
            if db.has_table(conn, "riot_mains"):
                for c in checks:
                    if c.fetched:
                        recorded += db.insert_riot_mains(
                            conn, riot_id=c.fetched["riot_id"], resolved=c.fetched["resolved"],
                            tag_guessed=c.fetched["tag_guessed"], fetched_at=c.fetched["fetched_at"],
                            mains=c.fetched["mains"], source="fetched")
            print(f"\nstored mains for {written} session(s); {recorded} new fetch(es) in riot_mains")
    return 0


def _coplay_crawl(args: argparse.Namespace) -> int:
    from r3m import coplay
    coplay.crawl(args.platform, args.target, progress=lambda m: print(m, flush=True), apex=args.apex)
    return 0


def _coplay_analyse(args: argparse.Namespace) -> int:
    from r3m import coplay
    coplay.analyse(progress=lambda m: print(m, flush=True))
    return 0


def _mains_import(args: argparse.Namespace) -> int:
    """Move the fetches in the local cache (data/panel-mains.json) into
    riot_mains -- one row per account and fetch time, so an account cached
    under several sessions becomes one row."""
    cache = panel.load_cache()
    if not cache:
        print("nothing cached")
        return 0
    with db.connect() as conn:
        if not db.has_table(conn, "riot_mains"):
            print("riot_mains needs migration 024 on this database. Nothing imported.")
            return 1
        fetches = {}
        for entry in cache.values():
            fetches.setdefault((db.riot_key(entry["riot_id"]), entry.get("fetched_at")), entry)
        added = 0
        for (_, fetched_at), e in sorted(fetches.items(), key=lambda kv: str(kv[0])):
            if not fetched_at:
                print(f"  {e['riot_id']}: no fetch time in the cache, skipped")
                continue
            new = db.insert_riot_mains(conn, riot_id=e["riot_id"], resolved=e.get("resolved"),
                                       tag_guessed=bool(e.get("tag_guessed")), fetched_at=fetched_at,
                                       mains=[tuple(m) for m in e["mains"]], source="cache")
            added += new
            print(f"  {e['riot_id']:20} -> {e.get('resolved') or '?':20} {fetched_at}  "
                  f"{sum(m[2] for m in e['mains'])} games  {'added' if new else 'already there'}")
        print(f"{added} fetch(es) added from {len(cache)} cached session(s)")
    return 0


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
        "--effort", default=labeling_run.DEFAULT_EFFORT, choices=EFFORTS,
        help=f"output_config.effort, recorded on the label_run "
             f"(default: {labeling_run.DEFAULT_EFFORT})",
    )
    label_cmd.add_argument(
        "--prompt-version", default=labeling_run.PROMPT_VERSION,
        choices=sorted(labeling_run.PROMPTS),
        help=f"champion prompt (default: {labeling_run.PROMPT_VERSION}; v3 is the "
             f"validated production prompt, see docs/sub-traits.md)",
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
        "--effort", default=labeling_run.DEFAULT_EFFORT, choices=EFFORTS,
        help=f"output_config.effort (default: {labeling_run.DEFAULT_EFFORT})",
    )
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
        help="which prompt version's labels to grade (default: the canonical runs)",
    )
    check_cmd.add_argument(
        "--runs", help="grade exactly these label_run ids, e.g. a pilot (overrides --prompt-version)"
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

    export_cmd = sub.add_parser(
        "labels-export", help="write label runs and their labels to a file (for another database)"
    )
    export_cmd.add_argument("--runs", required=True, help="label_run ids, e.g. 28,29")
    export_cmd.add_argument("--out", required=True, help="output JSON path")
    export_cmd.set_defaults(func=_labels_export)

    import_cmd = sub.add_parser(
        "labels-import", help="append label runs from an export; idempotent, touches nothing else"
    )
    import_cmd.add_argument("file", help="a labels-export JSON file")
    import_cmd.set_defaults(func=_labels_import)

    canonical_cmd = sub.add_parser(
        "canonical", help="show or change which label runs are served"
    )
    canonical_cmd.add_argument("--champion-runs", help="label_run ids to serve for champions, e.g. 9,10")
    canonical_cmd.add_argument("--game-runs", help="label_run ids to serve for games, e.g. 17")
    canonical_cmd.set_defaults(func=_canonical)

    candidates_cmd = sub.add_parser(
        "bank-candidates",
        help="propose the Steam portion of the game bank into bank/steam.yaml",
    )
    candidates_cmd.add_argument(
        "--csv", default=str(bank.STEAM_CSV),
        help="FronkonGames Steam dataset CSV (download: see r3m.bank)",
    )
    candidates_cmd.set_defaults(func=_bank_candidates)

    import_cmd = sub.add_parser(
        "bank-import", help="load bank/hand.yaml and bank/steam.yaml into the game table"
    )
    import_cmd.set_defaults(func=_bank_import)

    panel_cmd = sub.add_parser(
        "panel-check",
        help="compare panel quiz results with the champions each player really plays",
    )
    panel_cmd.add_argument(
        "--write", action="store_true",
        help="store each player's mains on their session and new fetches in riot_mains "
             "(default: report only)",
    )
    panel_cmd.add_argument(
        "--all", action="store_true", help="include sessions already checked"
    )
    panel_cmd.add_argument(
        "--refetch", action="store_true",
        help="ignore stored and cached mains and fetch from Riot again",
    )
    panel_cmd.set_defaults(func=_panel_check)

    mains_cmd = sub.add_parser(
        "mains-import",
        help="move the cached Riot fetches (data/panel-mains.json) into the riot_mains table",
    )
    mains_cmd.set_defaults(func=_mains_import)

    coplay_cmd = sub.add_parser("coplay-crawl", help="co-play experiment: crawl champion mastery (local DB)")
    coplay_cmd.add_argument("--platform", default="euw1")
    coplay_cmd.add_argument("--target", type=int, default=5000)
    coplay_cmd.add_argument("--apex", action="store_true", help="Master+ players, kept apart from the mid-ladder sample")
    coplay_cmd.set_defaults(func=_coplay_crawl)
    sub.add_parser("coplay-analyse", help="co-play experiment: Q1 and Q2 per role (local DB)").set_defaults(func=_coplay_analyse)
    sub.add_parser("coplay-checks2", help="co-play: melee/ranged, difficulty, label correction (local DB)").set_defaults(func=lambda a: (__import__("r3m.coplay", fromlist=["x"]).checks2(progress=lambda m: print(m, flush=True)), 0)[1])
    sub.add_parser("families", help="co-play families per role, stability, panel feasibility (local DB; analysis only)").set_defaults(func=lambda a: (__import__("r3m.families", fromlist=["x"]).run(panel_file=__import__("os").environ.get("PANEL_FILE"), progress=lambda m: print(m, flush=True)), 0)[1])
    sub.add_parser("families-feasibility", help="score panel players against saved families (PANEL_FILE; local DB)").set_defaults(func=lambda a: (__import__("r3m.families", fromlist=["x"]).feasibility(__import__("os").environ["PANEL_FILE"], progress=lambda m: print(m, flush=True)), 0)[1])
    sub.add_parser("coplay-spread", help="co-play: within-role spread of player pools in MMM vs a popularity null (local DB)").set_defaults(func=lambda a: (__import__("r3m.coplay", fromlist=["x"]).spread_check(progress=lambda m: print(m, flush=True)), 0)[1])
    sub.add_parser("coplay-checks", help="co-play: class-tag baseline, tier split, Master+ (local DB)").set_defaults(func=lambda a: (__import__("r3m.coplay", fromlist=["x"]).checks(progress=lambda m: print(m, flush=True)), 0)[1])

    place_cmd = sub.add_parser(
        "place", help="walk the podcast anchor candidates and place them by hand"
    )
    place_cmd.add_argument(
        "--purists", action="store_true",
        help="only the class purists — extremes by construction, and what the "
             "anchor set is shortest of",
    )
    place_cmd.add_argument("--role", help="only one role (mid, jungle, top, bot, support)")
    place_cmd.add_argument(
        "--restore", action="store_true",
        help="replay anchors/placements.log back into the worksheet",
    )
    place_cmd.add_argument(
        "--review", action="store_true",
        help="also revisit entries that are placed but have no tier yet",
    )
    place_cmd.set_defaults(func=_place)

    args = parser.parse_args()
    try:
        return args.func(args)
    finally:
        fetch.close()
