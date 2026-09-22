"""Command line entry point."""

import argparse
import time

import httpx

from r3m import anchors, db, fetch, ingest, sample
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
    return 1 if result.failed else 0


def _check_anchors(args: argparse.Namespace) -> int:
    result = anchors.check(label_run_id=args.run)
    print(
        f"label_run {result.label_run_id}  prompt {result.prompt_version}  "
        f"{result.model}\n"
    )

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

    check_cmd = sub.add_parser(
        "check-anchors", help="compare a labelling run against anchors/champions.yaml"
    )
    check_cmd.add_argument(
        "--run", type=int, default=None,
        help="label_run id (default: the latest run that produced labels)",
    )
    check_cmd.set_defaults(func=_check_anchors)

    args = parser.parse_args()
    try:
        return args.func(args)
    finally:
        fetch.close()
