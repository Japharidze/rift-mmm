"""Move label runs from one database to another: labels-only, append-only.

Labelling runs locally; production holds panel sessions that nothing else can
regenerate. A dump/restore would clobber them (and `restore` refuses a
non-empty database anyway), so new labels reach production this way instead:

    local:       r3m labels-export --runs 28,29,31 --out dumps/labels-<date>.json
    production:  r3m labels-import dumps/labels-<date>.json
                 r3m canonical --champion-runs <new id> --game-runs <new ids>

Import appends: each run gets a new label_run row with the target database's
own id, and its labels point at that id. Nothing existing is changed, so panel
data is untouched. It is idempotent -- a run already present in the target
(same prompt version, model and start time) is skipped -- so an interrupted or
repeated import is safe. Games must already exist in the target (`r3m
bank-import` first); champions do after any ingest of the same patch.

Scores travel as the exact decimal strings the database holds, and each run
carries a checksum over them, recomputed after import: a transfer that altered
a single label fails loudly rather than serving it.
"""

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from r3m.db import CHAMPION_LABEL_COLUMNS, _GAME_LABEL_COLUMNS

FORMAT = 1
_KEYS = {"champion": ("champion_id", "role"), "game": ("game_id",)}
_TABLE = {"champion": "champion_label", "game": "game_label"}


def _columns(kind: str) -> list[str]:
    cols = CHAMPION_LABEL_COLUMNS if kind == "champion" else _GAME_LABEL_COLUMNS
    return [*_KEYS[kind], *cols, "raw_response", "labelled_at"]


def _plain(v: Any) -> Any:
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def checksum(labels: list[dict[str, Any]], kind: str) -> str:
    """Over the identity and every score of every label, order-independent."""
    cols = CHAMPION_LABEL_COLUMNS if kind == "champion" else _GAME_LABEL_COLUMNS
    scored = [c for c in cols if c != "rationale"]
    lines = sorted(
        "|".join(str(l[k]) for k in _KEYS[kind]) + "|" +
        "|".join("" if l.get(c) is None else str(Decimal(str(l[c])).normalize()) for c in scored)
        for l in labels
    )
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _kind(cur: psycopg.Cursor, run_id: int) -> str:
    cur.execute("select exists (select 1 from champion_label where label_run_id = %s)", (run_id,))
    if cur.fetchone()[0]:  # type: ignore[index]
        return "champion"
    cur.execute("select exists (select 1 from game_label where label_run_id = %s)", (run_id,))
    if cur.fetchone()[0]:  # type: ignore[index]
        return "game"
    raise ValueError(f"label_run {run_id} has no labels")


def export_runs(conn: psycopg.Connection, run_ids: list[int]) -> dict[str, Any]:
    out: dict[str, Any] = {"format": FORMAT, "exported_at": datetime.now().astimezone().isoformat(),
                           "runs": []}
    with conn.cursor() as cur:
        for rid in run_ids:
            cur.execute("select id, prompt_version, model, effort, started_at, note "
                        "from label_run where id = %s", (rid,))
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"no label_run {rid}")
            kind = _kind(cur, rid)
            cols = _columns(kind)
            cur.execute(f"select {', '.join(cols)} from {_TABLE[kind]} where label_run_id = %s "
                        f"order by {', '.join(_KEYS[kind])}", (rid,))
            labels = [{c: _plain(v) for c, v in zip(cols, r)} for r in cur.fetchall()]
            run = dict(zip(("id", "prompt_version", "model", "effort", "started_at", "note"),
                           map(_plain, row)))
            out["runs"].append({"kind": kind, "run": run, "labels": labels,
                                "checksum": checksum(labels, kind)})
    return out


def write(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False))


def read(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if data.get("format") != FORMAT:
        raise ValueError(f"{path}: unknown export format {data.get('format')!r}")
    return data


def import_runs(conn: psycopg.Connection, data: dict[str, Any]) -> list[dict[str, Any]]:
    """Append each run and its labels; returns one report line per run."""
    report = []
    for entry in data["runs"]:
        kind, run, labels = entry["kind"], entry["run"], entry["labels"]
        if checksum(labels, kind) != entry["checksum"]:
            raise ValueError(f"export of run {run['id']} is corrupt: checksum mismatch")
        with conn.transaction(), conn.cursor() as cur:
            cur.execute("select id from label_run where prompt_version = %s and model = %s "
                        "and started_at = %s", (run["prompt_version"], run["model"], run["started_at"]))
            existing = cur.fetchone()
            if existing:
                report.append({"source": run["id"], "target": existing[0], "kind": kind,
                               "rows": len(labels), "status": "already present, skipped"})
                continue
            note = (run.get("note") or "") + f" [imported from label_run {run['id']}]"
            cur.execute("insert into label_run (prompt_version, model, effort, started_at, note) "
                        "values (%s, %s, %s, %s, %s) returning id",
                        (run["prompt_version"], run["model"], run["effort"], run["started_at"], note.strip()))
            new_id = cur.fetchone()[0]  # type: ignore[index]
            cols = _columns(kind)
            role_cast = "%s::role_t" if kind == "champion" else "%s"
            marks = ", ".join(role_cast if c == "role" else "%s" for c in cols)
            cur.executemany(
                f"insert into {_TABLE[kind]} (label_run_id, {', '.join(cols)}) values (%s, {marks})",
                [(new_id, *(Jsonb(l[c]) if c == "raw_response" else l[c] for c in cols)) for l in labels],
            )
            # Read back what landed and prove it is what left.
            cur.execute(f"select {', '.join(cols)} from {_TABLE[kind]} where label_run_id = %s", (new_id,))
            landed = [{c: _plain(v) for c, v in zip(cols, r)} for r in cur.fetchall()]
            if checksum(landed, kind) != entry["checksum"]:
                raise ValueError(f"run {run['id']}: labels changed in transit; rolled back")
        report.append({"source": run["id"], "target": new_id, "kind": kind,
                       "rows": len(labels), "status": "imported, checksum verified"})
    return report
