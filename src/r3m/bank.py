"""The game bank: where its games come from and how they reach the database.

Three portions (bank/hand.yaml says why): Steam games, ranked by lifetime reach
from a public dataset; off-Steam video games; and classic board, card and party
games. The last two are hand-picked in bank/hand.yaml. The Steam portion is
generated here into bank/steam.yaml, which is then read and trimmed by a person
before anything is imported -- the generator proposes, it does not decide.

The dataset is FronkonGames/steam-games-dataset on Hugging Face (MIT), about
126k published games with lifetime review counts, owner estimates, median
playtime and tags. Download once into data/ (gitignored, ~400 MB):

    curl -L -o data/steam-games.csv \\
      https://huggingface.co/datasets/FronkonGames/steam-games-dataset/resolve/main/games.csv

Two faults in it, both handled in read_steam:

- The CSV header fuses "Discount" and "DLC count" into one name, so every row
  has one more field than the header. Read naively, every column from there on
  is shifted by one and "Positive" holds the wrong number.
- Stats lag for new releases: Hollow Knight: Silksong, Battlefield 6 and ARC
  Raiders show zero reviews while Steam's own recommendation count is filled.
  Reach is therefore the larger of the two.

Why lifetime reach and not a live player count: the segment is 14-30, and the
question is whether someone that age *has played* a game, which includes what
they played at 15. A 24-hour snapshot misses every game that was huge in 2016.
"""

import csv
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from r3m import db
from r3m.config import DATA_DIR, ROOT

STEAM_CSV = DATA_DIR / "steam-games.csv"
BANK_DIR = ROOT / "bank"
HAND_FILE = BANK_DIR / "hand.yaml"
STEAM_FILE = BANK_DIR / "steam.yaml"
# Bias-proneness per game (docs/quiz-chain.md §5). Kept out of steam.yaml so
# re-running the generator cannot wipe hand judgments.
BIAS_FILE = BANK_DIR / "bias.yaml"
BIAS_LEVELS = ("low", "medium", "high")
# Recognition prior for the hand-picked games (migration 018); Steam games use
# their lifetime reach instead.
RENOWN_FILE = BANK_DIR / "renown.yaml"
RENOWN_LEVELS = ("universal", "wide", "niche")
GAME_ANCHORS = ROOT / "anchors" / "games.yaml"

# Deck entries from Steam, existing Steam-backed games included. With ~35 video
# and ~35 classic from hand.yaml that is the agreed ~300.
STEAM_TARGET = 230
# Proposed but unticked, so a cut can be swapped for the next in line without
# re-running anything.
RESERVE = 80
# Lifetime reviews (or recommendations). ~1000 games clear it, so the cut to
# 230 is made by reach and spread, not by this floor.
MIN_REACH = 20_000
# The segment is 14-30: born ~1996-2012, playing from ~2004 on. Applied to a
# franchise's most-played entry, so Counter-Strike (2000) still arrives as CS2.
FIRST_YEAR = 2004
# Minutes. Below this a game was owned rather than played: bundle and
# free-weekend inflation. Zero means unknown and is let through.
MIN_MEDIAN_MINUTES = 60
# Deck entries per genre bucket. The top of Steam is shooters and survival
# crafting; without a cap the deck would be that, and an eclectic deck is the
# point. Tuned so the cap binds on the crowded buckets only.
GENRE_CAP = 16

NON_GAME_GENRES = {
    "Utilities", "Software", "Animation & Modeling", "Design & Illustration",
    "Video Production", "Audio Production", "Photo Editing", "Web Publishing",
    "Game Development", "Education", "Accounting",
}

# Steam tags in vote order are the best genre signal the dataset has, but the
# first tag is often not a genre ("Free to Play", "Great Soundtrack", "Early
# Access"). So a game's bucket is the first of its tags found here.
GENRES: dict[str, set[str]] = {
    "moba": {"MOBA"},
    "battle-royale": {"Battle Royale"},
    "hero-shooter": {"Hero Shooter"},
    "tactical-shooter": {"Tactical"},
    "shooter": {"FPS", "Shooter", "Looter Shooter", "Third-Person Shooter", "Arena Shooter"},
    "soulslike": {"Souls-like"},
    "survival-craft": {"Open World Survival Craft", "Survival", "Crafting", "Base-Building"},
    "horror": {"Survival Horror", "Psychological Horror", "Horror"},
    "roguelike": {"Action Roguelike", "Rogue-like", "Rogue-lite", "Roguelike Deckbuilder",
                  "Deckbuilding", "Bullet Hell"},
    "fighting": {"Fighting", "2D Fighter", "Martial Arts", "Spectacle fighter", "Beat 'em up"},
    "racing": {"Racing", "Driving", "Automobile Sim"},
    "sports": {"Sports", "Football (Soccer)", "Basketball", "Golf", "Skateboarding"},
    "rts": {"RTS"},
    "strategy": {"Turn-Based Strategy", "Grand Strategy", "4X", "Wargame", "Turn-Based Tactics",
                 "Strategy"},
    "auto-battler": {"Auto Battler"},
    "tower-defense": {"Tower Defense"},
    "card-board": {"Card Game", "Trading Card Game", "Board Game", "Chess"},
    "builder": {"City Builder", "Colony Sim", "Automation", "Management", "Resource Management",
                "Economy"},
    "sim": {"Farming Sim", "Life Sim", "Flight", "Hunting", "Simulation"},
    "mmo": {"MMORPG", "Massively Multiplayer"},
    "action-rpg": {"Action RPG", "Hack and Slash", "Dungeon Crawler"},
    "rpg": {"JRPG", "CRPG", "Party-Based RPG", "Turn-Based Combat", "RPG"},
    "platformer": {"Platformer", "Puzzle-Platformer", "2D Platformer", "3D Platformer",
                   "Metroidvania", "Precision Platformer"},
    "puzzle": {"Puzzle"},
    "rhythm": {"Rhythm", "Music"},
    "party": {"Party Game", "Party", "Social Deduction"},
    "sandbox": {"Sandbox", "Physics", "Building"},
    "stealth": {"Stealth"},
    "narrative": {"Visual Novel", "Walking Simulator", "Point & Click", "Choices Matter",
                  "Story Rich", "Interactive Fiction"},
    "idle": {"Idler", "Clicker"},
}
TAG_TO_GENRE = {tag: bucket for bucket, tags in GENRES.items() for tag in tags}
FALLBACK_GENRE = "action-adventure"

_ROMAN = r"(?:ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii)"
_EDITION = re.compile(
    r"\b(legacy|remastered|definitive|enhanced|goty|game of the year|edition|complete|"
    r"deluxe|hd|classic|online|reloaded|x|anniversary)\b"
)
_DISPLAY_SUFFIX = re.compile(
    r"[\s:\-]+(Legacy|Enhanced( Edition)?|Remastered|Definitive Edition|Game of the Year( Edition)?|"
    r"GOTY( Edition)?|Complete Edition|Anniversary Edition|\d{4} Edition)$",
    re.IGNORECASE,
)
# Store entries that are not the game itself but share its name.
_NOT_THE_GAME = re.compile(
    r"\b(playtest|demo|friend'?s pass|test server|public test|dedicated server|soundtrack)\b"
    r"|\(retired\)",
    re.IGNORECASE,
)


def _plain(name: str) -> str:
    """Symbols and curly quotes out: Sid Meier’s and Sid Meier's are one publisher."""
    n = re.sub(r"[™®©]", "", name)
    return n.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')


def franchise(name: str) -> str:
    """A key shared by a game, its sequels and its re-releases.

    Deliberately blunt: drop the subtitle, edition words and a trailing sequel
    number. It over-groups on shared settings (Warhammer 40,000 is a shooter, a
    co-op game, a CRPG and an RTS), which _groups corrects with a tag check.
    """
    n = _plain(name).lower()
    n = re.sub(r"\([^)]*\)", " ", n)
    n = re.split(r"\s*[:\-–—]\s+", n)[0]
    n = _EDITION.sub("", n)
    n = re.sub(rf"\s+(\d+|{_ROMAN})\s*$", "", n.strip())
    n = re.sub(r"^(tom clancy'?s|sid meier'?s|the)\s+", "", n)
    n = re.sub(r"[^a-z0-9 ]", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    # EA renamed FIFA to EA SPORTS FC in 2023; one football series, one entry.
    n = re.sub(r"^ea sports ", "", n)
    return "fifa" if n == "fc" else n


def slug(name: str) -> str:
    s = _plain(name).lower().replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def display_name(name: str) -> str:
    n = re.sub(r"\s+", " ", _plain(name)).strip()
    return _DISPLAY_SUFFIX.sub("", n).strip(" :-")


def _year(s: str) -> int | None:
    for fmt in ("%b %d, %Y", "%b %Y", "%d %b, %Y"):
        try:
            return datetime.strptime(s.strip(), fmt).year
        except ValueError:
            pass
    return None


def _int(s: str) -> int:
    try:
        return int(s)
    except ValueError:
        return 0


def read_steam(path: Path = STEAM_CSV) -> list[dict[str, Any]]:
    """Every row of the dataset, header repaired, reach and tags parsed."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Download it first (see the r3m.bank docstring)."
        )
    csv.field_size_limit(sys.maxsize)
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        if "DiscountDLC count" in header:
            i = header.index("DiscountDLC count")
            header[i:i + 1] = ["Discount", "DLC count"]
        rows = []
        for raw in reader:
            if len(raw) != len(header):
                continue
            g = dict(zip(header, raw))
            reviews = _int(g["Positive"]) + _int(g["Negative"])
            rows.append({
                "appid": _int(g["AppID"]),
                "name": g["Name"],
                "year": _year(g["Release date"]),
                "reach": max(reviews, _int(g["Recommendations"])),
                "median_minutes": _int(g["Median playtime forever"]),
                "genres": set(filter(None, g["Genres"].split(","))),
                "tags": [t for t in g["Tags"].split(",") if t],
            })
    return rows


def genre(tags: list[str]) -> str:
    return next((TAG_TO_GENRE[t] for t in tags if t in TAG_TO_GENRE), FALLBACK_GENRE)


def _excluded(g: dict[str, Any]) -> str | None:
    """Why a title cannot be a deck candidate, or None."""
    if g["genres"] & NON_GAME_GENRES or _NOT_THE_GAME.search(g["name"]):
        return "not a game"
    top = g["tags"][:8]
    if "Hentai" in g["tags"] or ("Sexual Content" in top[:5] and "Nudity" in top):
        return "adult"
    if "VR" in g["tags"][:3]:
        return "VR only"
    if 0 < g["median_minutes"] < MIN_MEDIAN_MINUTES:
        return "owned, not played"
    return None


def _same_game(a: list[str], b: list[str]) -> bool:
    """Whether two titles sharing a name can be told apart by their tags.

    Missing tags cannot tell anything apart, so they count as the same game:
    the rows whose stats lag (FC 25, Silksong) arrive with no tags at all, and
    treating them as distinct listed EA SPORTS FC 24 three times.
    """
    sa, sb = set(a[:6]), set(b[:6])
    if not sa or not sb:
        return True
    return len(sa & sb) / len(sa | sb) >= 0.25


def _shared_prefix(a: str, b: str) -> str:
    out = []
    for x, y in zip(a.split(), b.split()):
        if x != y:
            break
        out.append(x)
    return " ".join(out)


@dataclass
class Group:
    """One game as the deck sees it: its most-played entry plus what collapsed into it."""
    head: dict[str, Any]
    collapsed: list[dict[str, Any]] = field(default_factory=list)

    @property
    def reach(self) -> int:
        return self.head["reach"]

    @property
    def tags(self) -> list[str]:
        """The head's tags, or the first member's that has any."""
        return next((m["tags"] for m in (self.head, *self.collapsed) if m["tags"]), [])


def _groups(rows: list[dict[str, Any]]) -> dict[str, Group]:
    """Collapse sequels and re-releases, keyed by franchise.

    A title joins a franchise only if its tags overlap the head's; otherwise it
    is a different game in the same setting and keeps a group of its own
    (Warhammer 40,000: Darktide is not Space Marine 2).
    """
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for g in rows:
        by_key[franchise(g["name"])].append(g)

    # A sequel whose subtitle has no colon keeps a key of its own ("dying light
    # 2 stay human"). Keys sharing a leading phrase of two words and nine
    # characters are the same series -- long enough that "age of" (Empires,
    # Wonders, Mythology) and "world of" (Tanks, Warships) stay apart.
    keys = sorted(by_key)
    root = {k: k for k in keys}

    def find(k: str) -> str:
        while root[k] != k:
            k = root[k]
        return k

    for i, a in enumerate(keys):
        if not a:
            continue
        for b in keys[i + 1:]:
            p = _shared_prefix(a, b)
            if len(p.split()) < 2 or len(p) < 9:
                if not b.startswith(a.split()[0]):
                    break  # sorted: nothing further shares even the first word
                continue
            ta = max(by_key[a], key=lambda g: g["reach"])["tags"]
            tb = max(by_key[b], key=lambda g: g["reach"])["tags"]
            if _same_game(ta, tb):
                root[find(b)] = find(a)
    merged: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for k in keys:
        merged[find(k)].extend(by_key[k])

    out: dict[str, Group] = {}
    for key, members in merged.items():
        members.sort(key=lambda g: -g["reach"])
        heads: list[Group] = []
        for g in members:
            # An identical name is the same game whatever its tags say: Steam
            # lists Portal 2 under two app ids whose tags overlap only 0.2.
            home = next((h for h in heads
                         if display_name(h.head["name"]) == display_name(g["name"])
                         or _same_game(h.tags, g["tags"])), None)
            if home:
                home.collapsed.append(g)
            else:
                heads.append(Group(head=g))
        out[key] = heads[0]
        for h in heads[1:]:
            out[f"{key}#{h.head['appid']}"] = h
    return out


def _hand_entries(hand: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    out = []
    for section, entries in hand.items():
        for e in entries:
            out.append({**e, "section": section})
    return out


@dataclass
class Proposal:
    selected: list[dict[str, Any]]
    reserve: list[dict[str, Any]]
    dropped: Counter
    genre_counts: Counter
    capped: Counter


def propose(rows: list[dict[str, Any]], hand: dict[str, Any], anchors: list[dict[str, Any]]
            ) -> Proposal:
    """The Steam portion: forced anchors, then greedy by reach under the genre cap."""
    hand_entries = _hand_entries(hand)
    hand_keys = {franchise(e["name"]) for e in hand_entries}
    hand_appids = {a for e in hand_entries for a in e.get("steam", [])}
    hand_ids = {e["id"] for e in hand_entries}

    # Existing games not owned by hand.yaml are the Steam-backed ones. They are
    # in the bank already, so they are kept whatever their stats say (Overwatch
    # 2's row carries zero reviews).
    steam_anchors = {franchise(a["name"]): a for a in anchors if a["id"] not in hand_ids}

    groups = _groups([g for g in rows if g["reach"] >= MIN_REACH])
    dropped: Counter = Counter()
    forced: dict[str, Group] = {}
    pool: list[Group] = []
    for key, grp in groups.items():
        base = key.split("#")[0]
        if grp.head["appid"] in hand_appids or base in hand_keys:
            dropped["in hand.yaml"] += 1
            continue
        anchor = steam_anchors.get(base) or next(
            (a for k, a in steam_anchors.items()
             if len(k.split()) >= 2 and base.startswith(k + " ")), None)
        if anchor and "#" not in key and anchor["id"] not in forced:
            forced[anchor["id"]] = grp
            continue
        why = _excluded({**grp.head, "tags": grp.tags})
        if why is None and (grp.head["year"] or 0) < FIRST_YEAR:
            why = f"before {FIRST_YEAR}"
        if why:
            dropped[why] += 1
            continue
        pool.append(grp)

    # An anchor below the reach floor still needs its Steam id for cover art.
    for key, a in steam_anchors.items():
        if a["id"] not in forced:
            hits = [g for g in rows if franchise(g["name"]) == key]
            if hits:
                forced[a["id"]] = Group(head=max(hits, key=lambda g: g["reach"]))

    def entry(grp: Group, gid: str, name: str, anchor: bool) -> dict[str, Any]:
        h = grp.head
        e = {
            "id": gid, "name": name, "steam": h["appid"],
            # An anchor's year is whatever the database holds; a Steam sequel's
            # year would be a wrong answer for a series (009_game_art.sql).
            "year": None if anchor else h["year"],
            "reach": h["reach"], "genre": genre(grp.tags), "tags": grp.tags[:5],
        }
        if grp.collapsed:
            e["collapsed"] = [display_name(c["name"]) for c in grp.collapsed[:6]]
        if anchor:
            e["existing"] = True
        return e

    counts: Counter = Counter()
    selected = []
    for a in anchors:
        if a["id"] in forced:
            e = entry(forced[a["id"]], a["id"], a["name"], anchor=True)
            counts[e["genre"]] += 1
            selected.append(e)

    taken_ids = hand_ids | {e["id"] for e in selected}
    capped: Counter = Counter()
    overflow = []
    for grp in sorted(pool, key=lambda g: -g.reach):
        name = display_name(grp.head["name"])
        gid = slug(name)
        if gid in taken_ids:
            gid = f"{gid}-{grp.head['appid']}"
        e = entry(grp, gid, name, anchor=False)
        if len(selected) < STEAM_TARGET and counts[e["genre"]] < GENRE_CAP:
            counts[e["genre"]] += 1
            selected.append(e)
            taken_ids.add(gid)
        else:
            if len(selected) < STEAM_TARGET:
                capped[e["genre"]] += 1
            overflow.append(e)
    return Proposal(selected=selected, reserve=overflow[:RESERVE], dropped=dropped,
                    genre_counts=counts, capped=capped)


def load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def write_steam(p: Proposal, path: Path = STEAM_FILE) -> None:
    header = f"""\
# Steam portion of the game bank. GENERATED by `r3m bank-candidates` from the
# FronkonGames Steam dataset (see r3m.bank), then trimmed by hand.
#
# To review: set keep: false on anything that should not be on the deck, and
# keep: true on a reserve entry to swap it in. `r3m bank-import` loads only
# keep: true. Re-running the generator overwrites this file, so trim after the
# last run.
#
# Ranked by lifetime reach (reviews, or Steam recommendations where review
# stats lag), one entry per franchise, at most {GENRE_CAP} per genre bucket.
# `existing: true` marks games already in the bank; they stay regardless.
# `collapsed` lists sequels and re-releases folded into the entry.
"""
    body = {
        "selected": [{**e, "keep": True} for e in p.selected],
        "reserve": [{**e, "keep": False} for e in p.reserve],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(header + "\n")
        yaml.safe_dump(body, f, sort_keys=False, allow_unicode=True, width=100)


def candidates(csv_path: Path = STEAM_CSV) -> Proposal:
    rows = read_steam(csv_path)
    anchors = load_yaml(GAME_ANCHORS)["games"]
    p = propose(rows, load_yaml(HAND_FILE), anchors)
    write_steam(p)
    return p


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImportResult:
    deck: int
    deep: int
    inserted: int
    updated: int
    untracked: list[str]


def bank_entries() -> list[dict[str, Any]]:
    """Every game the files put in the bank, deck entries before their children."""
    entries = []
    for e in _hand_entries(load_yaml(HAND_FILE)):
        deep = e["section"] == "deep"
        entries.append({
            "id": e["id"], "name": e["name"], "mode": e.get("mode"),
            "tier": "deep" if deep else "deck", "parent_id": e.get("parent"),
            "steam_appid": (e.get("steam") or [None])[0], "release_year": e.get("year"),
            "reach": None,
        })
    for e in load_yaml(STEAM_FILE)["selected"] + load_yaml(STEAM_FILE)["reserve"]:
        if e.get("keep"):
            entries.append({
                "id": e["id"], "name": e["name"], "mode": None, "tier": "deck",
                "parent_id": None, "steam_appid": e["steam"], "release_year": e.get("year"),
                "reach": e.get("reach"),
            })

    ids = [e["id"] for e in entries]
    dupes = [i for i, n in Counter(ids).items() if n > 1]
    if dupes:
        raise ValueError(f"ids appear twice across bank files: {dupes}")
    known = set(ids)

    bias = load_bias()
    stray = sorted(set(bias) - known)
    if stray:
        raise ValueError(f"{BIAS_FILE.name} rates games not in the bank: {stray}")
    for e in entries:
        e["bias"] = bias.get(e["id"])
    renown = load_levels(RENOWN_FILE, RENOWN_LEVELS)
    stray = sorted(set(renown) - known)
    if stray:
        raise ValueError(f"{RENOWN_FILE.name} rates games not in the bank: {stray}")
    for e in entries:
        e["renown"] = renown.get(e["id"])
    orphans = [e["id"] for e in entries if e["parent_id"] and e["parent_id"] not in known]
    if orphans:
        raise ValueError(f"parent not in the bank for: {orphans}")
    return sorted(entries, key=lambda e: e["parent_id"] is not None)


def import_bank(conn) -> ImportResult:
    entries = bank_entries()
    existing = db.game_ids(conn)
    for e in entries:
        db.upsert_bank_game(conn, **{("game_id" if k == "id" else k): v for k, v in e.items()})
    conn.commit()
    ids = {e["id"] for e in entries}
    return ImportResult(
        deck=sum(e["tier"] == "deck" for e in entries),
        deep=sum(e["tier"] == "deep" for e in entries),
        inserted=len(ids - existing),
        updated=len(ids & existing),
        untracked=sorted(existing - ids),
    )


def load_bias(path: Path = BIAS_FILE) -> dict[str, str]:
    """game id -> low / medium / high. A game rated twice is an error."""
    return load_levels(path, BIAS_LEVELS)


def load_levels(path: Path, levels: tuple[str, ...]) -> dict[str, str]:
    """game id -> level, from a file grouped by level. A game rated twice is an error."""
    if not path.exists():
        return {}
    data = load_yaml(path) or {}
    out: dict[str, str] = {}
    for level, games in data.items():
        if level not in levels:
            raise ValueError(f"{path.name}: unknown level {level!r}")
        for gid in games or {}:
            if gid in out:
                raise ValueError(f"{path.name}: {gid} rated twice")
            out[gid] = level
    return out
