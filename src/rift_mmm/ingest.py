"""One ingest run: Data Dragon entries, cleaned, into Postgres.

Pure composition — the fetching, cleaning and SQL all live elsewhere.
"""

from dataclasses import dataclass

from rift_mmm import data_dragon, db, kit_text


@dataclass(frozen=True)
class IngestResult:
    version: str
    champions: int


def run(version: str | None = None) -> IngestResult:
    """Ingest one patch, defaulting to the latest published.

    Fetching finishes before the transaction opens. ~170 requests can stall for
    minutes on a bad network, and a database transaction is not something to
    hold open across that. The entries are small enough to keep in memory.

    The write is a single transaction: a half-ingested patch whose `patch` row
    exists but whose champions are missing would make the next run skip work it
    never did.
    """
    version = version or data_dragon.latest_version()
    entries = list(data_dragon.champions(version))

    with db.connect() as conn, conn.transaction():
        db.upsert_patch(conn, version)
        for champion_id, entry in entries:
            db.upsert_champion(
                conn,
                champion_id=champion_id,
                riot_key=int(entry["key"]),  # Data Dragon ships this as a string
                name=entry["name"],
                title=entry["title"],
                tags=entry["tags"],
                partype=entry["partype"],
                patch_version=version,
            )
            db.upsert_champion_patch(
                conn,
                champion_id=champion_id,
                patch_version=version,
                raw=entry,
                kit_text=kit_text.build(entry),
            )

    return IngestResult(version=version, champions=len(entries))
