"""Data-only dumps, so a device change does not cost another labelling run.

Schema is not dumped: it comes from migrations, which stay the single source of
truth. Restoring is `migrate` then `restore`, and a dump can never carry a
schema that drifted from the migration files.

What is actually irreplaceable here:

- **labels** — champion_label and game_label are API spend, ~$8 so far.
- **match_participant** — a 45-minute crawl needing a Riot key that expires
  daily, and re-crawling draws a *different* random sample, so role shares
  would shift. Reproducibility, not just time.
- **champion_patch.raw** — Data Dragon rotates old patches off the CDN, which
  is why the column exists at all.

champion_role and the views regenerate from the above, but they are small and
dumping them keeps a restore complete in one step.
"""

import gzip
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from r3m.config import ROOT, settings

DUMP_DIR = ROOT / "dumps"


def _env() -> dict[str, str]:
    import os

    return {**os.environ, "PGPASSWORD": settings.postgres_password}


def _args() -> list[str]:
    return [
        "--host", settings.postgres_host,
        "--port", str(settings.postgres_port),
        "--username", settings.postgres_user,
        "--dbname", settings.postgres_db,
    ]


def dump(path: Path | None = None, force: bool = False) -> Path:
    """Write a gzipped data-only dump, named by date.

    Same-day dumps replace each other rather than piling near-identical blobs
    into git — which is fine on one machine and dangerous across two. If
    labelling ran elsewhere, was dumped, and committed, then dumping here
    silently overwrites work this database has never seen. That happened on
    2026-09-23: a dump carrying two extra runs and 53 extra labels was
    replaced by a smaller one, and only the git blob made it recoverable.

    So a dump that would drop rows the existing file has is refused. The
    comparison counts rows rather than bytes: gzip output varies by tens of
    bytes for identical data, so a size check false-positives on every ordinary
    re-dump. `force` overrides once you have looked.
    """
    DUMP_DIR.mkdir(exist_ok=True)
    path = path or DUMP_DIR / f"{datetime.now(UTC):%Y-%m-%d}.sql.gz"
    result = subprocess.run(
        [
            "pg_dump", "--data-only", "--no-owner", "--no-privileges",
            # schema_migrations is excluded on purpose: a restore target has
            # already run `migrate`, so those rows exist. Including them makes
            # psql abort on a duplicate key -- and because pg_dump puts setval
            # at the end, the abort silently leaves every sequence unset, so
            # the first insert after a restore collides on id=1.
            "--exclude-table=schema_migrations",
            *_args(),
        ],
        env=_env(), capture_output=True, check=True,
    )
    if path.exists() and not force:
        existing = _counts_in(path.read_bytes())
        fresh = _counts_in(gzip.compress(result.stdout))
        lost = {t: (existing[t], fresh[t]) for t in existing if fresh[t] < existing[t]}
        if lost:
            detail = ", ".join(f"{t} {a} -> {b}" for t, (a, b) in lost.items())
            raise RuntimeError(
                f"{path.name} holds rows this database does not: {detail}. "
                "Another machine probably dumped work that was never restored "
                "here. `git log -- dumps/` shows its history; restore it first, "
                "or pass --force if you are sure."
            )

    with gzip.open(path, "wb") as fh:
        fh.write(result.stdout)
    return path


# The tables whose loss would actually cost something. Counted rather than
# weighed, so ordinary gzip variation cannot trip the guard.
_GUARDED = ("champion_label", "game_label", "label_run", "match_participant")


def _counts_in(blob: bytes) -> dict[str, int]:
    """Rows per guarded table inside a gzipped pg_dump, without a database."""
    text = gzip.decompress(blob).decode(errors="replace")
    counts = {}
    for table in _GUARDED:
        marker = f"COPY public.{table} ("
        start = text.find(marker)
        if start == -1:
            counts[table] = 0
            continue
        body = text[text.index("\n", start) + 1:]
        counts[table] = body[: body.index("\n\\.")].count("\n") + 1
    return counts


def latest() -> Path | None:
    dumps = sorted(DUMP_DIR.glob("*.sql.gz")) if DUMP_DIR.exists() else []
    return dumps[-1] if dumps else None


def row_counts() -> dict[str, int]:
    from r3m import db

    tables = ("champion", "champion_patch", "match", "match_participant",
              "champion_role", "label_run", "champion_label", "game", "game_label")
    with db.connect() as conn, conn.cursor() as cur:
        out = {}
        for t in tables:
            cur.execute(f"select count(*) from {t}")  # noqa: S608 - fixed list
            out[t] = cur.fetchone()[0]  # type: ignore[index]
        return out


def restore(path: Path) -> None:
    """Load a dump into an already-migrated, empty database.

    Refuses a non-empty target: a data-only dump appends, so restoring over
    existing rows would duplicate them rather than replace them.
    """
    counts = row_counts()
    if any(counts.values()):
        filled = ", ".join(f"{t}={n}" for t, n in counts.items() if n)
        raise RuntimeError(
            f"target database is not empty ({filled}). A data-only dump appends, "
            "so this would duplicate rows. Drop and re-create the database, run "
            "`r3m migrate`, then restore."
        )
    with gzip.open(path, "rb") as fh:
        sql = fh.read()
    result = subprocess.run(
        ["psql", "--quiet", "--set", "ON_ERROR_STOP=1", *_args()],
        env=_env(), input=sql, capture_output=True,
    )
    if result.returncode != 0:
        # Surfaced rather than swallowed: the first version of this hid a
        # duplicate-key abort behind a bare CalledProcessError, and the restore
        # looked like it had worked because the rows were there.
        raise RuntimeError(
            f"psql exited {result.returncode}\n"
            + result.stderr.decode(errors="replace").strip()
        )
