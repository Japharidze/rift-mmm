"""The co-play experiment (2026-10-01): does champion choice follow any taste?

Round 2's first players' mains were as spread out in the labelled MMM space
as random champions. Before deciding whether to stop the project, this asks
real players' pools -- champion mastery, not our labels -- two questions, per
role:

  Q1  Do pools show taste beyond popularity? Pair co-occurrence against a
      null that keeps each champion's popularity and each pool's size.
  Q2  Only if Q1 holds: does that taste follow MMM label distance?

Decision rules are fixed in CLAUDE.md ("Current phase").

Separate from everything the quiz serves: its own tables, created here rather
than by a migration, and written to whatever database is configured -- run it
against the local one (DATABASE_URL= ...). No LLM, dev key only.
"""

from datetime import UTC, datetime
from itertools import zip_longest
from typing import Any, Iterator

from r3m import db
from r3m.riot_api import RiotApi
from r3m.sample import DEFAULT_SEEDS

SCHEMA = """
create table if not exists coplay_player (
    puuid        text primary key,
    platform     text not null,
    tier         text not null,
    division     text not null,
    seeded_at    timestamptz not null default now(),
    fetched_at   timestamptz,               -- null until mastery is stored
    n_champions  integer
);
create table if not exists coplay_mastery (
    puuid         text not null references coplay_player (puuid) on delete cascade,
    champion_key  integer not null,         -- champion.riot_key
    points        bigint not null,
    level         integer not null,
    last_play     timestamptz,
    primary key (puuid, champion_key)
);
create index if not exists coplay_player_platform on coplay_player (platform, fetched_at);
"""


def ensure_schema(conn: Any) -> None:
    conn.execute(SCHEMA)
    conn.commit()


def _ladder(api: RiotApi, seeds=DEFAULT_SEEDS) -> Iterator[tuple[str, str, str]]:
    """(puuid, tier, division), interleaved across the seed tiers page by page,
    as the match crawl does, so no single tier supplies the whole sample."""
    page = 1
    while True:
        ladders = []
        for tier, division in seeds:
            entries = api.league_entries(tier, division, page)
            ladders.append([(e["puuid"], tier, division) for e in entries if e.get("puuid")])
        if not any(ladders):
            return
        for row in zip_longest(*ladders):
            for player in row:
                if player is not None:
                    yield player
        page += 1


APEX = "MASTER+"   # tier stored for Master, Grandmaster and Challenger players


def _apex(api: RiotApi) -> Iterator[tuple[str, str, str]]:
    """Master+ players, Challenger first. A contrast sample, kept apart from
    the mid-ladder one in every analysis."""
    for tier in ("challenger", "grandmaster", "master"):
        for e in api.apex_league(tier):
            if e.get("puuid"):
                yield e["puuid"], APEX, "I"


def crawl(platform: str, target: int, progress=print, apex: bool = False) -> int:
    """Fetch mastery until `target` players of this platform are stored --
    mid-ladder, or Master+ with `apex`. Resumable: players already fetched are
    skipped, so a rerun continues."""
    api = RiotApi(platform=platform)
    with db.connect() as conn:
        ensure_schema(conn)
        done = conn.execute("select count(*) from coplay_player where platform = %s and fetched_at is not null"
                            " and (tier = %s) = %s", (platform, APEX, apex)).fetchone()[0]
        fetched = {r[0] for r in conn.execute("select puuid from coplay_player where fetched_at is not null")}
        for puuid, tier, division in (_apex(api) if apex else _ladder(api)):
            if done >= target:
                break
            if puuid in fetched:
                continue
            masteries = api.champion_masteries(puuid)
            conn.execute("""insert into coplay_player (puuid, platform, tier, division)
                            values (%s, %s, %s, %s) on conflict (puuid) do nothing""",
                         (puuid, platform, tier, division))
            with conn.cursor() as cur:
                cur.executemany(
                    """insert into coplay_mastery (puuid, champion_key, points, level, last_play)
                       values (%s, %s, %s, %s, %s) on conflict do nothing""",
                    [(puuid, m["championId"], m["championPoints"], m.get("championLevel", 0),
                      datetime.fromtimestamp(m["lastPlayTime"] / 1000, UTC) if m.get("lastPlayTime") else None)
                     for m in masteries])
            conn.execute("update coplay_player set fetched_at = now(), n_champions = %s where puuid = %s",
                         (len(masteries), puuid))
            conn.commit()
            fetched.add(puuid)
            done += 1
            if done % 250 == 0:
                progress(f"{platform}: {done}/{target} players")
    progress(f"{platform}: done, {done} players")
    return done


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

import math
import random
import statistics as st
from collections import Counter
from itertools import combinations

# A pool is a player's top POOL champions by mastery, with at least MIN_POINTS
# each (dabbling is not a pool). The recent pool keeps only champions played
# within RECENT_DAYS of the crawl: lifetime mastery measures time, not current
# taste.
POOL, MIN_POINTS, RECENT_DAYS = 5, 10_000, 365
# The main sample; Master+ (APEX) is a contrast, never mixed in.
MID_LADDER = ("GOLD", "PLATINUM", "EMERALD")
NULL_SAMPLES, LABEL_SHUFFLES = 100, 1000
# Q2 uses only pairs the null expects to see together at least this often --
# rarer pairs give a co-play score that is mostly noise.
MIN_EXPECTED = 2.0


def load(conn: Any, recent: bool, tiers: tuple[str, ...] | None = None) -> tuple[dict[str, list[tuple[str, set[str]]]], dict[str, tuple[float, float, float]]]:
    """Per role, each player's pool restricted to champions whose primary role
    it is; and each champion's canonical MMM point for that role."""
    key_to_id = dict(conn.execute("select riot_key, id from champion").fetchall())
    primary = dict(conn.execute("select champion_id, role from champion_role where is_primary").fetchall())
    points = {(r["champion_id"], r["role"]): (r["micro"], r["meso"], r["macro"]) for r in db.champion_points(conn)}
    label = {c: points[(c, role)] for c, role in primary.items() if (c, role) in points}
    cutoff = "and m.last_play > p.fetched_at - interval '%s days'" % RECENT_DAYS if recent else ""
    rows = conn.execute(f"""
        select m.puuid, m.champion_key, p.platform from coplay_mastery m join coplay_player p using (puuid)
        where m.points >= %s and p.tier = any(%s) {cutoff}
        order by m.puuid, m.points desc""", (MIN_POINTS, list(tiers or MID_LADDER))).fetchall()
    pools: dict[str, list[str]] = {}
    platform: dict[str, str] = {}
    for puuid, key, plat in rows:
        platform[puuid] = plat
        pool = pools.setdefault(puuid, [])
        if len(pool) < POOL and key_to_id.get(key) in label:
            pool.append(key_to_id[key])
    by_role: dict[str, list[tuple[str, set[str]]]] = {}
    for puuid, pool in pools.items():
        for role in Counter(primary[c] for c in pool):
            within = {c for c in pool if primary[c] == role}
            if len(within) >= 2:
                by_role.setdefault(role, []).append((platform[puuid], within))
    return by_role, label


def _pairs(rows: list[set[str]]) -> Counter:
    out: Counter = Counter()
    for row in rows:
        out.update(combinations(sorted(row), 2))
    return out


def _curveball(rows: list[set[str]], trades: int, rng: random.Random) -> None:
    """Strona et al.'s curveball: swap the non-shared members of two pools.
    Keeps every pool's size and every champion's count exactly."""
    n = len(rows)
    for _ in range(trades):
        i, j = rng.randrange(n), rng.randrange(n)
        if i == j:
            continue
        a, b = rows[i] - rows[j], rows[j] - rows[i]
        if not a or not b:
            continue
        common = rows[i] & rows[j]
        mixed = list(a | b)
        rng.shuffle(mixed)
        rows[i], rows[j] = common | set(mixed[:len(a)]), common | set(mixed[len(a):])


def _rank(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2
        i = j + 1
    return r


def spearman(x: list[float], y: list[float]) -> float:
    rx, ry = _rank(x), _rank(y)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else 0.0


def role_test(rows: list[set[str]], label: dict, seed: int = 0, q2: bool = True) -> dict[str, Any]:
    rng = random.Random(seed)
    observed = _pairs(rows)
    null_rows = [set(r) for r in rows]
    _curveball(null_rows, 20 * len(rows), rng)            # burn-in
    samples = []
    for _ in range(NULL_SAMPLES):
        _curveball(null_rows, 5 * len(rows), rng)
        samples.append(_pairs(null_rows))
    keys = set(observed) | {k for s in samples for k in s}
    mean = {k: st.mean(s.get(k, 0) for s in samples) for k in keys}
    sd = {k: st.pstdev([s.get(k, 0) for s in samples]) or 1.0 for k in keys}
    chi = lambda c: sum((c.get(k, 0) - mean[k]) ** 2 / mean[k] for k in keys if mean[k] > 0)
    s_obs, s_null = chi(observed), [chi(s) for s in samples]
    z = {k: (observed.get(k, 0) - mean[k]) / sd[k] for k in keys}
    usable = [k for k in keys if mean[k] >= MIN_EXPECTED]
    # How many 3-sd pairs a random world produces on its own, for comparison.
    null_strong = st.mean(sum(1 for k in usable if (s.get(k, 0) - mean[k]) / sd[k] > 3) for s in samples)
    out = {"players": len(rows), "champions": len({c for r in rows for c in r}),
           "excess": s_obs / st.mean(s_null), "p": (1 + sum(s >= s_obs for s in s_null)) / (1 + len(s_null)),
           "strong_pairs": sum(1 for k in usable if z[k] > 3), "null_strong": null_strong,
           "pairs": len(usable), "z": {k: z[k] for k in usable}}
    if not q2:
        return out
    # Q2: does co-play affinity (z) follow MMM closeness?
    champs = sorted({c for k in usable for c in k})
    def rho(lab: dict, dim: int | None) -> float:
        close = [-(math.dist(lab[a], lab[b]) if dim is None else abs(lab[a][dim] - lab[b][dim])) for a, b in usable]
        return spearman([z[k] for k in usable], close)
    out["rho"] = {}
    if len(usable) < 10:                                  # too few pairs to correlate
        return out
    for name, dim in (("all", None), ("micro", 0), ("meso", 1), ("macro", 2)):
        real = rho(label, dim)
        perms = []
        for _ in range(LABEL_SHUFFLES):
            vals = [label[c] for c in champs]; rng.shuffle(vals)
            perms.append(rho(dict(zip(champs, vals)), dim))
        out["rho"][name] = (real, (1 + sum(p >= real for p in perms)) / (1 + len(perms)))
    return out


def analyse(progress=print) -> None:
    with db.connect() as conn:
        n = conn.execute("select platform, count(*) from coplay_player where fetched_at is not null group by 1").fetchall()
        progress(f"players: {dict(n)}")
        for recent in (False, True):
            by_role, label = load(conn, recent)
            progress(f"\n{'RECENT (last %d days)' % RECENT_DAYS if recent else 'LIFETIME'} pools: top {POOL} by mastery, >= {MIN_POINTS} points")
            progress(f"{'role':8} {'players':>7} {'champs':>6} {'excess':>6} {'EUNE':>5} {'EUW':>5} "
                     f"{'3sd pairs (null)':>17} {'replication rho (p)':>20}   Q2 rho (p): all / micro / meso / macro")
            for role in ("top", "jungle", "mid", "bot", "support"):
                tagged = by_role.get(role, [])
                rows = [r for _, r in tagged]
                if len(rows) < 50:
                    progress(f"{role:8} too few players ({len(rows)})"); continue
                r = role_test(rows, label)
                # Replication: the same test on each region alone; real taste
                # shows the same pairs in both, flukes do not.
                parts = {p: role_test([x for q, x in tagged if q == p], label, q2=False)
                         for p in ("eun1", "euw1") if sum(q == p for q, _ in tagged) >= 50}
                rep = "-"
                if len(parts) == 2:
                    common = sorted(set(parts["eun1"]["z"]) & set(parts["euw1"]["z"]))
                    if len(common) >= 10:
                        a = [parts["eun1"]["z"][k] for k in common]; b = [parts["euw1"]["z"][k] for k in common]
                        real = spearman(a, b); rng = random.Random(1); perms = []
                        for _ in range(LABEL_SHUFFLES):
                            rng.shuffle(b); perms.append(spearman(a, b))
                        rep = f"{real:+.2f} ({(1 + sum(x >= real for x in perms)) / (1 + len(perms)):.3f}) n={len(common)}"
                ex = {p: f"{v['excess']:.2f}" for p, v in parts.items()}
                q2 = " / ".join(f"{v[0]:+.2f} ({v[1]:.3f})" for v in r["rho"].values()) or "too few pairs"
                progress(f"{role:8} {r['players']:7} {r['champions']:6} {r['excess']:6.2f} {ex.get('eun1', '-'):>5} {ex.get('euw1', '-'):>5} "
                         f"{r['strong_pairs']:5} ({r['null_strong']:4.1f})/{r['pairs']:<5} {rep:>20}   {q2}")


# ---------------------------------------------------------------------------
# Checks after the first results (2026-10-02): a class-tag baseline, a tier
# split, a Master+ contrast.
# ---------------------------------------------------------------------------

def _pearson(x: list[float], y: list[float]) -> float:
    mx, my = st.mean(x), st.mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den = math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))
    return num / den if den else 0.0


def _partial(x: list[float], y: list[float], z: list[float]) -> float:
    """Spearman correlation of x and y with z partialled out, on ranks."""
    rx, ry, rz = _rank(x), _rank(y), _rank(z)
    xy, xz, yz = _pearson(rx, ry), _pearson(rx, rz), _pearson(ry, rz)
    den = math.sqrt(max(1e-12, (1 - xz * xz) * (1 - yz * yz)))
    return (xy - xz * yz) / den


def tag_test(z: dict, label: dict, tags: dict[str, set[str]], seed: int = 0) -> dict[str, Any]:
    """Does MMM explain co-play beyond Riot's class tags? Per dimension: tags
    alone, MMM alone, and MMM with tag similarity partialled out -- the last
    against 1,000 shuffles of the MMM labels with the tags left in place."""
    rng = random.Random(seed)
    pairs = [k for k in z if k[0] in tags and k[1] in tags]
    zs = [z[k] for k in pairs]
    tag_sim = [len(tags[a] & tags[b]) / len(tags[a] | tags[b]) for a, b in pairs]
    champs = sorted({c for k in pairs for c in k})
    def close(lab: dict, dim: int | None) -> list[float]:
        return [-(math.dist(lab[a], lab[b]) if dim is None else abs(lab[a][dim] - lab[b][dim])) for a, b in pairs]
    out = {"pairs": len(pairs), "tags": spearman(zs, tag_sim)}
    for name, dim in (("all", None), ("micro", 0), ("meso", 1), ("macro", 2)):
        real = _partial(zs, close(label, dim), tag_sim)
        perms = []
        for _ in range(LABEL_SHUFFLES):
            vals = [label[c] for c in champs]; rng.shuffle(vals)
            perms.append(_partial(zs, close(dict(zip(champs, vals)), dim), tag_sim))
        out[name] = (spearman(zs, close(label, dim)), real,
                     (1 + sum(p >= real for p in perms)) / (1 + len(perms)))
    return out


ROLES = ("top", "jungle", "mid", "bot", "support")


def checks(progress=print) -> None:
    with db.connect() as conn:
        tags = {c: set(t or []) for c, t in conn.execute("select id, tags from champion").fetchall()}
        by_role, label = load(conn, recent=False)
        progress("CHECK 1 -- class-tag baseline (lifetime pools, mid-ladder). Spearman with co-play:")
        progress("  tags = tag similarity alone; MMM = label closeness alone; MMM|tags = MMM with tags partialled out (p)")
        progress(f"{'role':8} {'pairs':>5} {'tags':>6}   {'all: MMM  MMM|tags':>22} {'micro':>20} {'meso':>20} {'macro':>20}")
        for role in ROLES:
            rows = [r for _, r in by_role.get(role, [])]
            r = role_test(rows, label, q2=False)
            t = tag_test(r["z"], label, tags)
            cell = lambda v: f"{v[0]:+.2f} {v[1]:+.2f} ({v[2]:.3f})"
            progress(f"{role:8} {t['pairs']:5} {t['tags']:+6.2f}   {cell(t['all']):>22} {cell(t['micro']):>20} "
                     f"{cell(t['meso']):>20} {cell(t['macro']):>20}")

        progress("\nCHECK 2 -- tier split (lifetime pools). Q1 excess, 3-sd pairs (null), Q2 rho all / micro / meso / macro")
        for tier in MID_LADDER + (APEX,):
            by_tier, _ = load(conn, recent=False, tiers=(tier,))
            for role in ROLES:
                rows = [r for _, r in by_tier.get(role, [])]
                if len(rows) < 50:
                    progress(f"{tier:9} {role:8} too few players ({len(rows)})"); continue
                r = role_test(rows, label)
                q2 = " / ".join(f"{v[0]:+.2f}" for v in r["rho"].values()) or "too few pairs"
                progress(f"{tier:9} {role:8} {len(rows):5} players  excess {r['excess']:5.2f}  "
                         f"3sd {r['strong_pairs']:3} ({r['null_strong']:.1f})/{r['pairs']:<4}  Q2 {q2}")
