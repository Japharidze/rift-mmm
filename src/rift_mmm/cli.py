"""Command line entry point."""

import argparse
import time

import httpx

from rift_mmm import db, fetch, ingest, sample
from rift_mmm.migrate import apply_migrations
from rift_mmm.riot_api import RiotApi


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


def main() -> int:
    parser = argparse.ArgumentParser(prog="rift-mmm")
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

    args = parser.parse_args()
    try:
        return args.func(args)
    finally:
        fetch.close()
