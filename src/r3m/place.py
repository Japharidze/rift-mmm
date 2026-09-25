"""Interactive placement of anchor candidates.

`anchors/candidates.yaml` holds 62 champions the podcast named, each with the
coaches' own description of what its class demands and no scores. This walks
them one at a time and asks for three buckets.

Why a walker rather than editing the file: 186 values is a keyboard task, and
hand-editing YAML invites the two failure modes that matter -- drifting into
numbers instead of buckets, which claims precision the judgment does not have,
and losing your place, which makes it tempting to hurry the tail.

Nothing here suggests a value. A model-set anchor cannot test a model, and five
dimensions of the existing set are already `provisional` for exactly that
reason. The coaches answered "what does this champion demand"; the part left is
"which of the three is that", and it has to come from a person.

Writes after every champion, so quitting mid-way loses nothing and re-running
resumes where you stopped.
"""

from __future__ import annotations

import json
from typing import Any

import yaml

from r3m.config import ROOT

CANDIDATES = ROOT / "anchors" / "candidates.yaml"
# Append-only journal beside the worksheet. The worksheet is rewritten in
# place, so anything that clobbers the file -- a bad edit, a `git checkout`
# over uncommitted work -- takes every placement with it. This has cost real
# work once. The journal is never rewritten, only appended, so a lost
# worksheet is a replay rather than a redo: `r3m place --restore`.
JOURNAL = ROOT / "anchors" / "placements.log"
TRANSCRIPT = ROOT / "docs" / "transcripts" / "02-champion-classes.md"

# The order is the prompt: 1 is most, 5 is least, and the keys sit under one
# hand so a long session stays a rhythm rather than a lookup.
KEYS = {
    "1": "high",
    "2": "mid-high",
    "3": "mid",
    "4": "low-mid",
    "5": "low",
    # The source is silent on this dimension. An anchor does not need all
    # three: anchors.check skips any dimension that is not a mapping, so a
    # champion anchored on macro alone is a perfectly good macro test.
    #
    # This key exists because the one-line `demands` describes what makes a
    # class *distinctive*, which is usually one dimension. Asking for three
    # anyway turns two of them into guesses -- Syndra's class line is "saying
    # no; knowing your spikes; summoner intentionality", which says nothing
    # about execution, and the guess it forced was the single largest
    # disagreement in the first eighteen. A blank is worth more than a filler.
    "0": None,
}
# Asked before the three buckets, and it sets the tier the anchor lands at.
#
# It exists to take the pressure off. Without it every placement is implicitly
# blocking, so a champion you have never played feels like a trap -- which is
# exactly the moment a careful person stops, and the moment a careless one
# guesses. A `wide` anchor is reported and never blocks, so being unsure costs
# nothing and is worth recording rather than skipping: the coaches' description
# is evidence even when your memory is not.
PLAYED = {
    "y": "tight",   # played it; own judgment, blocking
    "n": "wide",    # knows the role, has not played it; reported, not blocking
}

DIMS = (
    ("micro", "execution — aim, timing, combos, skillshots, spacing"),
    ("meso", "reading people — fog, bluffing, threat, when to show yourself"),
    ("macro", "planning — wincon, tempo, routing, waves, objectives, saying no"),
)


def _load() -> dict[str, Any]:
    return yaml.safe_load(CANDIDATES.read_text())


def _write(doc: dict[str, Any], placed: dict[tuple[str, str], dict[str, str]]) -> None:
    """Rewrite the file in place, preserving its header comments.

    The header explains the bucket vocabulary and why a model must not fill
    these in; a yaml.dump round-trip would silently drop all of it.
    """
    text = CANDIDATES.read_text()
    head = text.split("\ncandidates:", 1)[0]
    lines = [head, "\ncandidates:"]
    for c in doc["candidates"]:
        got = placed.get((c["id"], c["role"]), {})
        lines.append(f"  - id: {c['id']}")
        lines.append(f"    role: {c['role']}")
        for d, _ in DIMS:
            # "none" means asked and answered: the source does not speak to it.
            # Distinct from TODO, which means not yet looked at.
            lines.append(f"    {d}: {got.get(d, c[d]) if (c['id'], c['role']) not in placed or d in got else 'none'}")
        lines.append(f"    tier: {got.get('tier', c.get('tier', 'TODO'))}")
        lines.append(f"    class: {c['class']}")
        # json, not yaml.safe_dump: dumping a bare scalar appends a "..."
        # document-end marker, which splits the file in two and makes
        # everything after the first entry a second document. A JSON string is
        # a valid YAML double-quoted scalar and has no such tail.
        lines.append(f"    demands: {json.dumps(c['demands'])}")
        lines.append(f"    live_roles: [{', '.join(c['live_roles'])}]")
        # `or "null"`: a bare None interpolates as the string "None", which
        # YAML then reads back as a string, not a missing value.
        lines.append(f"    chapter_line: {c['chapter_line'] if c['chapter_line'] is not None else 'null'}")
        if c.get("note"):
            lines.append(f"    note: {json.dumps(c['note'])}")
        lines.append("")
    CANDIDATES.write_text("\n".join(lines))


def _journal(champion: str, role: str, got: dict[str, str]) -> None:
    with JOURNAL.open("a") as fh:
        cells = "\t".join(got.get(d, "none") for d, _ in DIMS)
        fh.write(f"{champion}\t{role}\t{cells}\t{got['tier']}\n")


def restore() -> int:
    """Replay the journal back into the worksheet.

    Last entry per champion x role wins, so a champion placed twice keeps the
    later answer.
    """
    if not JOURNAL.exists():
        print("no journal to restore from")
        return 1
    placed: dict[tuple[str, str], dict[str, str]] = {}
    for line in JOURNAL.read_text().splitlines():
        if not line.strip():
            continue
        champ, role, mi, me, ma, tier = line.split("\t")
        placed[(champ, role)] = {"micro": mi, "meso": me, "macro": ma, "tier": tier}
    doc = _load()
    _write(doc, placed)
    print(f"restored {len(placed)} placements from the journal")
    return 0


def _chapter(line_no: object, n: int = 40) -> str:
    """The transcript around a class chapter, or a plain note if we have none.

    line_no arrives from YAML and has been a string before now: the writer
    below used to interpolate Python's None into "chapter_line: None", which
    round-tripped as the *string* "None" and crashed here on `"None" - 1`.
    Three playmaker supports carried it -- the rows most worth checking
    against the transcript.
    """
    try:
        start = int(line_no)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "  (no transcript reference recorded for this class)"
    lines = TRANSCRIPT.read_text().splitlines()
    return "\n".join(lines[max(0, start - 1): start - 1 + n])


def run(*, purists_only: bool = False, role: str | None = None,
        review: bool = False) -> int:
    doc = _load()
    todo = [
        c for c in doc["candidates"]
        if (any(c[d] == "TODO" for d, _ in DIMS)
            or (review and c.get("tier", "TODO") == "TODO"))
        and (not purists_only or "purist" in c["class"])
        and (role is None or c["role"] == role)
    ]
    done = sum(1 for c in doc["candidates"] if all(c[d] != "TODO" for d, _ in DIMS))
    if not todo:
        print("nothing left to place with that filter")
        return 0

    print(f"{len(todo)} to place, {done} already done.")
    print("keys: 1 high  2 mid-high  3 mid  4 low-mid  5 low")
    print("      0 the source does not say — leave this one unanchored")
    print("      t show what the coaches said   s skip   q save and quit\n")

    placed: dict[tuple[str, str], dict[str, str]] = {}
    for i, c in enumerate(todo, 1):
        print("-" * 68)
        star = " *PURIST*" if "purist" in c["class"] else ""
        print(f"[{i}/{len(todo)}]  {c['id']}  ({c['role']}){star}")
        print(f"  class   : {c['class']}")
        print(f"  demands : {c['demands']}")
        if c["role"] not in c["live_roles"]:
            print(f"  note    : podcast discusses it {c['role']}, match data says "
                  f"{', '.join(c['live_roles']) or 'not live'}")

        # Already placed and only missing a tier: ask that and nothing else.
        # Re-asking for buckets somebody has already decided invites them to
        # second-guess a judgment that was fine, and turns an 18-keystroke
        # repair into a 72-keystroke one.
        settled = all(c[d] != "TODO" for d, _ in DIMS)
        if settled:
            print(f"  placed   : {c['micro']} / {c['meso']} / {c['macro']}")

        tier = None
        while tier is None:
            raw = input("  played this one? (y/n, t transcript, s skip, q quit)\n  > ").strip().lower()
            if raw == "q":
                _write(doc, placed)
                print(f"\nsaved. {len(placed)} placed this session.")
                return 0
            if raw == "s":
                break
            if raw == "t":
                print(_chapter(c["chapter_line"]))
                continue
            tier = PLAYED.get(raw)
            if tier is None:
                print("    y / n, or t / s / q")
        if tier is None:
            continue

        if settled:
            got = {d: c[d] for d, _ in DIMS if c[d] != "none"}
            got["tier"] = tier
            placed[(c["id"], c["role"])] = got
            _journal(c["id"], c["role"], got)
            _write(doc, placed)
            print(f"  -> tier {tier}"
                  f"{'' if tier == 'tight' else ', reported not blocking'}")
            continue

        got: dict[str, str] = {}
        for d, gloss in DIMS:
            while True:
                raw = input(f"  {d:<6} ({gloss})\n  > ").strip().lower()
                if raw == "q":
                    _write(doc, placed)
                    print(f"\nsaved. {len(placed)} placed this session.")
                    return 0
                if raw == "s":
                    got = {}
                    break
                if raw == "t":
                    print(_chapter(c["chapter_line"]))
                    continue
                if raw in KEYS:
                    got[d] = KEYS[raw]
                    break
                print("    1-5, 0 for none, or t / s / q")
            if not got and d != DIMS[0][0]:
                break
            if not got:
                break
        if got and len(got) == len(DIMS):
            got = {k: v for k, v in got.items() if v is not None}
            if not got:
                print("  -> nothing the source supports; left unanchored")
                continue
            got["tier"] = tier
            placed[(c["id"], c["role"])] = got
            _journal(c["id"], c["role"], got)
            _write(doc, placed)
            blocking = "blocking" if tier == "tight" else "reported, not blocking"
            shown = " / ".join(got.get(d, "—") for d, _ in DIMS)
            print(f"  -> {shown}  [{tier}, {blocking}]")

    print(f"\ndone. {len(placed)} placed.")
    return 0
