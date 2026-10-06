"""Co-play families (2026-10-06, docs/families.md). Analysis only, local DB.

Per role, champions grouped by how often real players' pools hold them
together beyond popularity (the curveball z of r3m.coplay). Average-linkage
agglomeration on z, the number of families chosen by weighted modularity on
the positive-z graph. Then: stability across regions and eras, each family's
MMM profile, a scoring rule from a player's game answers to families, and a
feasibility check on the panel players with a Riot id.
"""

import json
import math
import random
import statistics as st
from collections import Counter
from itertools import combinations
from typing import Any

from r3m import coplay, db, deep_dives, quiz
from r3m.coplay import MID_LADDER, MIN_POINTS, POOL, ROLES, role_test, _fit

# A champion needs this many pools (2+ in the role) to be clustered; rarer ones
# are attached afterwards to the family they co-occur with most, and flagged.
MIN_PLAYERS = 30
K_RANGE = range(3, 11)
# Rule B's kernel width: how far from a loved game a champion still counts.
KERNEL_H = 0.15


def load_roles(conn: Any, era: tuple[int | None, int | None] | None = None
               ) -> tuple[dict[str, list[tuple[str, set[str]]]], dict[str, dict[str, tuple]]]:
    """Like coplay.load, but a champion counts in every role it has a row for
    (the 30% threshold), not only its primary, with that role's label."""
    key_to_id = dict(conn.execute("select riot_key, id from champion").fetchall())
    roles: dict[str, set[str]] = {}
    for c, r in conn.execute("select champion_id, role::text from champion_role").fetchall():
        roles.setdefault(c, set()).add(r)
    label: dict[str, dict[str, tuple]] = {}
    for r in db.champion_points(conn):
        label.setdefault(r["role"], {})[r["champion_id"]] = (r["micro"], r["meso"], r["macro"])
    cutoff = ""
    if era:
        within, older = era
        if within: cutoff += " and m.last_play > p.fetched_at - interval '%d days'" % within
        if older: cutoff += " and m.last_play <= p.fetched_at - interval '%d days'" % older
    rows = conn.execute(f"""
        select m.puuid, m.champion_key, p.platform from coplay_mastery m join coplay_player p using (puuid)
        where m.points >= %s and p.tier = any(%s) {cutoff}
        order by m.puuid, m.points desc""", (MIN_POINTS, list(MID_LADDER))).fetchall()
    pools: dict[str, list[str]] = {}
    platform: dict[str, str] = {}
    for puuid, key, plat in rows:
        platform[puuid] = plat
        pool = pools.setdefault(puuid, [])
        c = key_to_id.get(key)
        if len(pool) < POOL and c in roles:
            pool.append(c)
    by_role: dict[str, list[tuple[str, set[str]]]] = {}
    for puuid, pool in pools.items():
        for role in ROLES:
            within = {c for c in pool if role in roles[c] and c in label.get(role, {})}
            if len(within) >= 2:
                by_role.setdefault(role, []).append((platform[puuid], within))
    return by_role, label


def _sim(z: dict) -> Any:
    return lambda a, b: z.get((a, b) if a < b else (b, a), 0.0)


def agglomerate(champs: list[str], sim: Any) -> dict[int, list[list[str]]]:
    """Average linkage on similarity: the partition at every number of groups."""
    clusters = [[c] for c in champs]
    history = {len(clusters): [c[:] for c in clusters]}
    link = {(i, j): sim(clusters[i][0], clusters[j][0]) for i, j in combinations(range(len(clusters)), 2)}
    while len(clusters) > 1:
        (i, j), _ = max(link.items(), key=lambda kv: kv[1])
        merged = clusters[i] + clusters[j]
        rest = [c for n, c in enumerate(clusters) if n not in (i, j)]
        clusters = rest + [merged]
        n = len(clusters) - 1
        link = {}
        for a, b in combinations(range(len(clusters)), 2):
            link[(a, b)] = st.mean(sim(x, y) for x in clusters[a] for y in clusters[b])
        history[len(clusters)] = [c[:] for c in clusters]
    return history


def modularity(groups: list[list[str]], sim: Any) -> float:
    champs = [c for g in groups for c in g]
    w = {(a, b): max(sim(a, b), 0.0) for a, b in combinations(champs, 2)}
    m2 = 2 * sum(w.values()) or 1.0
    deg = Counter()
    for (a, b), v in w.items():
        deg[a] += v; deg[b] += v
    q = 0.0
    for g in groups:
        inside = 2 * sum(w.get((a, b) if (a, b) in w else (b, a), 0.0) for a, b in combinations(g, 2))
        q += inside / m2 - (sum(deg[c] for c in g) / m2) ** 2
    return q


def ari(x: dict[str, int], y: dict[str, int]) -> float:
    """Adjusted Rand index over the champions both partitions contain."""
    common = sorted(set(x) & set(y))
    if len(common) < 3:
        return float("nan")
    comb = lambda n: n * (n - 1) / 2
    table = Counter((x[c], y[c]) for c in common)
    a, b = Counter(x[c] for c in common), Counter(y[c] for c in common)
    s = sum(comb(v) for v in table.values())
    sa, sb, n = sum(comb(v) for v in a.values()), sum(comb(v) for v in b.values()), comb(len(common))
    expected = sa * sb / n
    top = (sa + sb) / 2
    return (s - expected) / (top - expected) if top != expected else 0.0


def _ari_null(x: dict[str, int], y: dict[str, int], rng: random.Random, n: int = 500) -> float:
    common = sorted(set(x) & set(y))
    ys = [y[c] for c in common]; out = []
    for _ in range(n):
        rng.shuffle(ys); out.append(ari({c: x[c] for c in common}, dict(zip(common, ys))))
    return sorted(out)[int(0.95 * n)]


BOOT = 100
MIN_EXPECTED = 2.0


def affinity(rows: list[list[str]]) -> dict[tuple[str, str], tuple[float, float]]:
    """Pair co-play against a closed-form null that keeps pool sizes and
    champion popularity: E(a,b) = n_a n_b T / S^2, S = sum of pool sizes,
    T = sum k(k-1). Returns (z, expected) per pair, z = (O - E) / sqrt(E).
    Deterministic and fast, so it can be bootstrapped; checked against the
    curveball z of r3m.coplay (docs/families.md)."""
    n = Counter(c for r in rows for c in r)
    S = sum(len(r) for r in rows); T = sum(len(r) * (len(r) - 1) for r in rows)
    obs: Counter = Counter()
    for r in rows:
        obs.update(combinations(sorted(r), 2))
    out = {}
    for a, b in combinations(sorted(n), 2):
        e = n[a] * n[b] * T / S ** 2
        out[(a, b)] = ((obs.get((a, b), 0) - e) / math.sqrt(e), e) if e > 0 else (0.0, 0.0)
    return out


def _cut(core: list[str], sim: Any, k: int | None) -> tuple[int, dict[int, float], list[list[str]]]:
    history = agglomerate(core, sim)
    curve = {n: modularity(history[n], sim) for n in K_RANGE if n in history}
    if k is None:
        k = max(curve, key=lambda n: (round(curve[n], 3), -n))
    return k, curve, history[min(k, len(core))]


def families_for(rows: list[set[str]], k: int | None = None, boot: int = BOOT, seed: int = 0) -> dict[str, Any]:
    """Cluster one role's pools by consensus: k chosen by modularity on the
    full data, then the same cut on `boot` resamples of players; champions
    grouped by how often they land together (average linkage on that rate)."""
    rng = random.Random(seed)
    rows = [sorted(r) for r in rows]
    aff = affinity(rows)
    z = {p: v[0] for p, v in aff.items()}
    count = Counter(c for r in rows for c in r)
    core = sorted(c for c in count if count[c] >= MIN_PLAYERS)
    k, curve, _ = _cut(core, _sim(z), k)
    together: Counter = Counter()
    for _ in range(boot):
        sample = [rows[rng.randrange(len(rows))] for _ in rows]
        zb = {p: v[0] for p, v in affinity(sample).items()}
        present = [c for c in core if any(c in p for p in zb)]
        _, _, groups = _cut(present, _sim(zb), k)
        for g in groups:
            together.update(combinations(sorted(g), 2))
    rate = {p: together[p] / boot for p in combinations(core, 2)}
    groups = agglomerate(core, _sim(rate))[min(k, len(core))]
    assign = {c: i for i, g in enumerate(groups) for c in g}
    # How firmly each champion sits in its family: mean co-assignment rate
    # with its family-mates across the resamples.
    firm = {c: st.mean(rate[tuple(sorted((c, m)))] for m in groups[assign[c]] if m != c)
            if len(groups[assign[c]]) > 1 else 0.0 for c in core}
    sim = _sim(z)
    attached = {c: max(range(len(groups)), key=lambda i: st.mean(sim(c, m) for m in groups[i]))
                for c in sorted(set(count) - set(core))}
    return {"k": k, "curve": curve, "groups": groups, "assign": assign, "attached": attached,
            "count": count, "firm": firm, "z": {p: v[0] for p, v in aff.items() if v[1] >= MIN_EXPECTED},
            "z_all": z}


def _profile(members: list[str], lab: dict) -> tuple[tuple[float, ...], float, tuple[float, ...]]:
    pts = [lab[c] for c in members if c in lab]
    centre = tuple(st.mean(p[i] for p in pts) for i in range(3))
    spread = st.mean(math.dist(p, centre) for p in pts)
    sd = tuple(st.pstdev([p[i] for p in pts]) for i in range(3))
    return centre, spread, sd


# ---------------------------------------------------------------------------
# The scoring rule (docs/families.md, step 2)
# ---------------------------------------------------------------------------

def score_a(est: quiz.Estimate, fam: dict) -> float:
    """Rule A: the player's point and its uncertainty against the family's
    centre and spread, on read dimensions only (never imputed). A Gaussian
    log-likelihood, -1/2 sum [(p - mu)^2 / v + log v], v = s^2 + u^2,
    u = sigma / sqrt(weight). The log term keeps a wide family from winning
    just by being wide."""
    total = 0.0
    for i, d in enumerate(quiz.DIMENSIONS):
        e = est.dimensions[d]
        if not e.read:
            continue
        v = fam["sd"][i] ** 2 + quiz.EVIDENCE_SIGMA ** 2 / max(e.informative, 1e-9)
        total -= 0.5 * ((e.value - fam["centre"][i]) ** 2 / v + math.log(v))
    return total


def score_b(est: quiz.Estimate, fam: dict, lab: dict) -> float:
    """Rule B (variant): each loved game pulls toward the family's members near
    it, each disliked game pushes away -- no single point, so two different
    loves can each find their own family. Ignores deep dives and comparisons."""
    k = lambda g: st.mean(math.exp(-math.dist(g, lab[c]) ** 2 / (2 * KERNEL_H ** 2)) for c in fam["members"])
    pt = lambda g: (g["micro"], g["meso"], g["macro"])
    return (sum(k(pt(g)) for g in est.loved)
            - quiz.DISLIKE_WEIGHT * sum(k(pt(g)) for g in est.disliked))


def run(panel_file: str | None = None, progress=print) -> None:
    rng = random.Random(0)
    with db.connect() as conn:
        by_role, label = load_roles(conn)
        old, _ = load_roles(conn, era=coplay.OLD_ERA)
        new, _ = load_roles(conn, era=coplay.RECENT_ERA)
        ranged = {c: r > 300 for c, r in conn.execute(
            "select distinct on (champion_id) champion_id, (raw->'stats'->>'attackrange')::int "
            "from champion_patch order by champion_id, patch_version desc").fetchall()}
        names = dict(conn.execute("select id, name from champion").fetchall())
        games = db.game_points(conn)

    progress("FAMILIES -- co-play clusters per role (mid-ladder, lifetime pools; a champion counts in every role it has a row for)")
    progress(f"  average linkage; k by weighted modularity over {K_RANGE.start}-{K_RANGE.stop - 1}; "
             f"core = {MIN_PLAYERS}+ pools, * = attached rare champion")
    progress(f"  consensus over {BOOT} player resamples (closed-form null); firmness = mean rate a member lands with its")
    progress("  family-mates across resamples; ? = member below 0.5")
    progress("  centre = mean MMM (micro/meso/macro), spread = mean distance to centre; canonical | co-play corrected (lam 1)")
    families: list[dict] = []
    for role in ROLES:
        rows = [r for _, r in by_role[role]]
        f = families_for(rows)
        lab = label[role]
        fitted = {**lab, **_fit(lab, {k: v for k, v in f["z"].items() if all(c in lab for c in k)}, 1.0)}
        curve = " ".join(f"{n}:{q:.3f}" for n, q in f["curve"].items())
        progress(f"\n{role.upper()}  players {len(rows)}, core {len(f['assign'])}, attached {len(f['attached'])}, "
                 f"k={f['k']}  (modularity {curve})")
        # Stability: the same k on each half and each era, against the full run and each other.
        parts = {}
        for name, sub in (("eune", [r for p, r in by_role[role] if p == "eun1"]),
                          ("euw", [r for p, r in by_role[role] if p == "euw1"]),
                          ("old", [r for _, r in old.get(role, [])]), ("recent", [r for _, r in new.get(role, [])])):
            parts[name] = families_for(sub, k=f["k"], boot=30)["assign"] if len(sub) >= 200 else {}
        full = f["assign"]
        stab = []
        for a, b in (("eune", "euw"), ("old", "recent"), ("eune", "full"), ("euw", "full"), ("old", "full"), ("recent", "full")):
            pa, pb = parts.get(a, full if a == "full" else {}), (full if b == "full" else parts[b])
            if pa and pb:
                stab.append(f"{a}~{b} {ari(pa, pb):.2f} (null95 {_ari_null(pa, pb, rng):.2f})")
            else:
                stab.append(f"{a}~{b} n/a")
        progress("  stability (adjusted Rand): " + "; ".join(stab))
        members_all: dict[int, list[str]] = {}
        for c, i in list(f["assign"].items()) + list(f["attached"].items()):
            members_all.setdefault(i, []).append(c)
        total = sum(f["count"].values())
        for i in sorted(members_all, key=lambda i: -sum(f["count"][c] for c in members_all[i])):
            mem = sorted(members_all[i], key=lambda c: -f["count"][c])
            core = [c for c in mem if c in f["assign"]]
            centre, spread, sd = _profile(core, lab)
            ccentre, cspread, _ = _profile(core, fitted)
            share_r = sum(ranged.get(c, False) for c in core) / len(core)
            pop = sum(f["count"][c] for c in mem) / total
            fam = {"role": role, "id": f"{role}-{sum(x['role'] == role for x in families) + 1}", "members": core, "attached": mem,
                   "centre": centre, "sd": sd, "spread": spread, "popularity": pop}
            families.append(fam)
            progress(f"  {fam['id']:10} pop {pop:4.0%}  {'ranged' if share_r > .66 else 'melee' if share_r < .34 else 'mixed'} "
                     f"({share_r:.0%} ranged)  canon {'/'.join(f'{v:.2f}' for v in centre)} spread {spread:.2f} | "
                     f"corr {'/'.join(f'{v:.2f}' for v in ccentre)} spread {cspread:.2f}")
            firm = st.mean(f["firm"][c] for c in core)
            progress(f"             firmness {firm:.2f}: " + ", ".join(
                names.get(c, c) + ("*" if c not in f["assign"] else "?" if f["firm"][c] < 0.5 else "") for c in mem))

    with open(FAMILIES_FILE, "w") as fh:
        json.dump(families, fh, indent=1)
    if panel_file:
        feasibility(panel_file, progress)


FAMILIES_FILE = "data/families-2026-10-06.json"


def feasibility(panel_file: str, progress=print) -> None:
    families = json.load(open(FAMILIES_FILE))
    with db.connect() as conn:
        games = db.game_points(conn)
        label: dict[str, dict[str, tuple]] = {}
        for r in db.champion_points(conn):
            label.setdefault(r["role"], {})[r["champion_id"]] = (r["micro"], r["meso"], r["macro"])
    progress("\nFEASIBILITY -- panel players with a Riot id (latest result session each; Sergi excluded)")
    progress("  true role = most games in their 40 recent games; true family = the family in that role holding most of")
    progress("  those games. Rank of the true family among all families (1 = top); chance = (F+1)/2.")
    F = len(families)
    lab_of = lambda fam: label[fam["role"]]
    out = []
    for s in json.load(open(panel_file)):
        reasons = s["reasons"] or {}
        try:
            est = quiz.estimate(s["loved"], s["disliked"] or [], rows=games, reasons=reasons)
        except ValueError:
            progress(f"  {s['k']}: no estimate"); continue
        est = deep_dives.settle(est, s["deep_dives"] or [], s["comparisons"] or [], games)
        # Only games on a champion some family holds in that role count: a
        # champion played off its rows (Kai'Sa mid) has no family to land in.
        per_fam, by_role_games = Counter(), Counter()
        for m in s["mains"]:
            for fam in families:
                if fam["role"] == m["role"] and m["champion_id"] in fam["attached"]:
                    per_fam[fam["id"]] += m["games"]; by_role_games[m["role"]] += m["games"]
        if not per_fam:
            progress(f"  {s['k']}: no family holds their champions"); continue
        true_role = by_role_games.most_common(1)[0][0]
        true_fam = max((f for f in per_fam if f.startswith(true_role)), key=lambda f: per_fam[f])
        rankings = {
            "A": sorted(families, key=lambda fam: -score_a(est, fam)),
            "A+pop": sorted(families, key=lambda fam: -(score_a(est, fam) + math.log(fam["popularity"]))),
            "B": sorted(families, key=lambda fam: -score_b(est, fam, lab_of(fam))),
            "popularity": sorted(families, key=lambda fam: -fam["popularity"]),
        }
        ranks = {n: [fam["id"] for fam in r].index(true_fam) + 1 for n, r in rankings.items()}
        role_rank = {n: list(dict.fromkeys(fam["role"] for fam in r)).index(true_role) + 1 for n, r in rankings.items()}
        read = "".join(d[:2] for d in quiz.DIMENSIONS if est.dimensions[d].read)
        out.append((ranks, role_rank))
        progress(f"  {s['k']:16} read {read:6} true {true_role}/{true_fam} ({per_fam[true_fam]}/{s['games']} games)  "
                 + "  ".join(f"{n} fam {ranks[n]:>2} role {role_rank[n]}" for n in rankings)
                 + f"   A top: {rankings['A'][0]['id']}")
    if out:
        progress(f"  mean rank of the true family (of {F}; chance {(F + 1) / 2:.1f}): "
                 + "  ".join(f"{n} {st.mean(o[0][n] for o in out):.1f}" for n in out[0][0]))
        progress(f"  mean rank of the true role (of 5; chance 3.0): "
                 + "  ".join(f"{n} {st.mean(o[1][n] for o in out):.1f}" for n in out[0][1]))
