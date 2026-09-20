"""Command line entry point."""

import argparse

from rift_mmm import db, fetch, ingest
from rift_mmm.migrate import apply_migrations


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

    args = parser.parse_args()
    try:
        return args.func(args)
    finally:
        fetch.close()
