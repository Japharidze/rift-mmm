# Co-play experiment — results (2026-10-02)

Question: does champion choice follow any taste, and is it the taste our MMM
labels describe? Data: champion mastery for 10,000 mid-ladder ranked players
(5,000 EUNE, 5,000 EUW; Emerald/Platinum/Gold II), crawled 2026-10-01.
Pools: each player's top 5 champions by mastery (≥10k points), split by the
champions' primary role; "recent" keeps only champions played in the last year.
Code: `src/r3m/coplay.py`; raw output: `docs/coplay-run-2026-10-02.txt`.
Decision rules were fixed beforehand (CLAUDE.md, Current phase).

## Q1 — within a role, is there taste? **Yes, in every role.**

| role | players | excess over null (EUNE / EUW) | 3-sd pairs (null) | EUNE↔EUW replication ρ |
|---|---|---|---|---|
| top | 2,353 | 2.9 (1.8 / 2.1) | 33 (2.2) | +0.44 |
| jungle | 2,448 | 2.9 (2.0 / 2.0) | 33 (1.9) | +0.58 |
| mid | 2,458 | 4.4 (2.3 / 3.3) | 37 (1.3) | +0.55 |
| bot | 3,385 | 4.8 (3.3 / 2.5) | 27 (0.8) | +0.67 |
| support | 2,435 | 5.8 (3.2 / 3.8) | 49 (1.6) | +0.60 |

Real pools hold 3–6× the pair structure of shuffles that keep every
champion's popularity and every pool's size; each region alone shows it; the
3-sd pairs outnumber what the shuffles produce by 15–35×; and the pair-level
pattern found on EUNE reappears on EUW (ρ 0.44–0.67, p ≤ 0.001 everywhere).
Recent pools give the same numbers (excess 2.8–5.8, replication 0.51–0.62), so
it is not release era. Judged on size and replication, not p-values.

## Q2 — does that taste follow MMM? **Partly: yes, weakly, carried by micro.**

Spearman ρ between a pair's co-play affinity and its closeness in the
canonical labels, against 1,000 label shuffles within the role (lifetime; recent
is the same within ±0.03):

| role | all | micro | meso | macro |
|---|---|---|---|---|
| top | **+0.32** | +0.35 | +0.18 | +0.03 |
| jungle | **+0.32** | +0.24 | +0.17 | +0.00 |
| mid | +0.14 | +0.19 | +0.09 | −0.02 |
| bot | +0.16 | +0.15 | +0.02 | +0.03 |
| support | +0.17 | +0.16 | +0.07 | +0.09 |

Positive and beyond the shuffles in every role (p ≤ 0.04), but modest. For
scale, the reproducible part of co-play (EUNE vs EUW) correlates at 0.44–0.67,
so the labels explain roughly half of it in top and jungle and a quarter in mid,
bot and support. **Micro carries it in every role; meso adds in top and jungle;
macro carries nothing within a role** — consistent with Gate 1, where macro
separated roles rather than champions inside one.

## What it means against the decision rules

**Q1 yes, Q2 yes (weak).** By the rule fixed in advance: the champion labels
hold, and the problem was "one point per player" — next design is role first,
then champions within the role. Two qualifications the rule did not foresee:

- Within a role, only micro (and meso in top/jungle) matches real taste; macro
  is a role axis, not a champion axis. A within-role matcher should weigh it
  accordingly — an evidence decision, so Sergi's.
- The labels explain at most about half of the reproducible taste. Real pools
  carry structure the three dimensions miss (theme, aesthetics, kit families).

## Risks, one line each

- Mid-ladder ranked players only; newcomers' taste may differ from experienced players'.
- Mastery is time-weighted: one-tricks and long accounts dominate a pool's top 5.
- Champions count only in their primary role; flex picks are lost.
- Co-play can also reflect shared kit families or skins, which MMM may only partly encode.
- Q2 uses pairs expected together at least twice; rare champions barely count.
- The p floor is 0.001 (1,000 shuffles); read sizes and replication, not p.

# Checks (2026-10-03)

Raw output: `docs/coplay-checks-2026-10-02.txt`. Lifetime pools.

## Check 1 — does MMM add anything beyond Riot's class tags? **Yes, in every role.**

Spearman with co-play. MMM|tags = MMM with tag similarity partialled out
(p against 1,000 label shuffles, tags fixed).

| role | tags alone | MMM alone | MMM\|tags | micro\|tags | meso\|tags | macro\|tags |
|---|---|---|---|---|---|---|
| top | +0.23 | +0.32 | **+0.31** (0.001) | +0.34 | +0.18 | +0.04 |
| jungle | +0.14 | +0.33 | **+0.31** (0.001) | +0.25 | +0.14 | −0.01 |
| mid | +0.32 | +0.13 | +0.12 (0.041) | +0.18 | +0.06 | −0.03 |
| bot | +0.19 | +0.17 | +0.19 (0.002) | +0.18 | +0.04 | +0.03 |
| support | +0.33 | +0.16 | +0.19 (0.002) | +0.17 | +0.11 | +0.06 |

MMM loses almost nothing when tags are removed: the two capture different
things. MMM is stronger than tags in top and jungle, tags are stronger in mid
and support, about equal in bot. Micro carries MMM's part everywhere.

## Check 2 — tier split. **Structure and the MMM link hold in every tier.**

| tier | Q1 3-sd pairs vs null (range over roles) | Q2 ρ all, by role (top/jg/mid/bot/sup) | micro |
|---|---|---|---|
| Gold | 6–21 vs 0.3–1.3 | .24 / .32 / .20 / .25 / .14 | .10–.32 |
| Platinum | 7–22 vs 0.5–1.4 | .29 / .36 / .12 / .12 / .14 | .12–.32 |
| Emerald | 9–23 vs 0.5–1.5 | .32 / .29 / .10 / .14 / .19 | .12–.34 |
| Master+ (contrast, 156–372 players/role) | 4–14 vs 0.2–0.6 | .22 / .31 / .05 / .22 / .20 | .13–.28 |

Not one end of the ladder: every tier shows it, Master+ included. (Excess
ratios are not comparable across tiers -- they grow with sample size.) One
pattern appears in every tier: macro tracks co-play in support (+0.12–0.23),
the only role where it does.

## Answer

MMM explains co-play beyond the class tags in every role and every tier, through
micro (meso in top and jungle). By Sergi's rule, the redesign candidate stands:
role first, champions within the role, matching on micro (and meso), co-play as
a second signal. Tags explain more than MMM in mid and support, so there the
two would be complementary rather than MMM alone.

Risks: tag similarity is coarse (≤2 tags per champion) and weak as a baseline;
the partial correlation is rank-based and linear; tiers share regions and
patch, so shared meta is still not ruled out.

# Reading of the pair lists (Sergi, 2026-10-03)

The strongest pairs per role are recognisable playstyle families: Irelia+Riven,
Yasuo+Zed+Katarina, the control mages, the enchanters, the hook supports. The
disagreements show what MMM misses:

- **Melee vs ranged.** Yasuo sits 0.09–0.14 from Xerath and Orianna in MMM, yet
  they are almost never in one pool.
- **Simplicity.** Garen+Malphite, Amumu+Rammus, Malzahar+Veigar cluster.
- **Over-separated families.** Nami+Yuumi sit 0.59 apart and are played together.

**Corrected ceiling:** MMM explains roughly 15% of the reliable co-play
structure in top and jungle, and 3–4% in mid, bot and support.

# Checks A–C (2026-10-03)

Raw output: `docs/coplay-checks2-2026-10-03.txt`. Lifetime pools, mid-ladder.
Partial correlations are Spearman on ranks; p against 1,000 shuffles of the
champion attribute.

## A — melee/ranged and the micro split. **The split carries part of range, not all.**

| role | melee/ranged | split AUC (ranged > melee) | split | split \| micro | range | range \| MMM, split |
|---|---|---|---|---|---|---|
| top | 37/5 | 0.69 | +0.14 | **+0.13** (0.001) | +0.07 | +0.09 (0.016) |
| jungle | 31/8 | 0.62 | +0.11 | **+0.14** (0.005) | +0.02 | −0.02 (0.72) |
| mid | 9/24 | 0.78 | +0.20 | **+0.22** (0.003) | +0.38 | **+0.37** (0.001) |
| bot | 1/25 | 0.76 | +0.16 | **+0.14** (0.016) | +0.01 | +0.03 (0.41) |
| support | 13/20 | 0.75 | +0.08 | +0.08 (0.065) | +0.25 | **+0.26** (0.001) |

The split leans ranged (AUC 0.62–0.78) and explains co-play beyond plain micro
in four roles of five. But in mid and support, melee/ranged explains a lot the
split and MMM don't (+0.37, +0.26); in top a little; in jungle and bot there
is almost no range variation to test.

## B — simplicity (Riot difficulty). **Adds nothing beyond MMM.**

| role | pairs | difficulty | difficulty \| MMM |
|---|---|---|---|
| top | 677 | +0.07 | +0.04 (0.16) |
| jungle | 581 | +0.15 | +0.06 (0.11) |
| mid | 378 | +0.06 | +0.07 (0.14) |
| bot | 274 | +0.14 | +0.12 (0.050) |
| support | 439 | +0.05 | +0.03 (0.26) |

Riot's difficulty rating doesn't capture the simplicity clusters, or MMM
already holds what it does capture.

## C — label correction, feasibility. **Small moves, large gains, validated across regions.**

Coordinates fitted to EUNE co-play, anchored to the current labels (λ), scored
on EUW: ρ(EUW co-play, closeness) and mean move per champion.

| role | current | λ 10 | λ 1 | λ 0.1 | most moved at λ 1 |
|---|---|---|---|---|---|
| top | +0.34 | +0.35 / 0.01 | **+0.39 / 0.07** | +0.46 / 0.19 | Kayle, Cho'Gath, Gangplank, Nasus |
| jungle | +0.23 | +0.25 / 0.01 | **+0.34 / 0.05** | +0.44 / 0.15 | Xin Zhao, Udyr, Viego, Lee Sin |
| mid | +0.09 | +0.12 / 0.01 | **+0.36 / 0.07** | +0.51 / 0.17 | Yasuo, Malzahar, Xerath, Anivia |
| bot | +0.18 | +0.20 / 0.01 | **+0.33 / 0.06** | +0.48 / 0.15 | Brand, Smolder, Samira, Varus |
| support | +0.16 | +0.18 / 0.01 | **+0.35 / 0.07** | +0.59 / 0.19 | Tahm Kench, Yuumi, Bard, Nami |

Moves of 0.05–0.07 per champion -- about one nearest-neighbour distance --
take held-out ρ to 0.33–0.39 in every role; moves of 0.15–0.19 reach 0.44–0.59,
the replication ceiling. Three dimensions are kept throughout.

## Answers

- **Range:** partly inside MMM via the split; in mid and support, not enough.
- **Difficulty:** doesn't explain co-play beyond MMM.
- **Co-play correcting the labels:** feasible within three dimensions with
  small moves, and it generalises across regions.

Risks: both regions share one patch, so a correction can learn the meta, not
taste; λ was not tuned, and 0.1 moves labels far enough to override the kit;
the range test has no power in jungle and bot (almost no variation); Data
Dragon difficulty is missing for some newer champions.

# Meta check (2026-10-05) — **co-play is mostly taste, not the current patch**

Raw output: `docs/coplay-meta-2026-10-05.txt`. Each player's pool split into
champions last played more than a year ago (old era) and within the last 90
days (recent era) -- different patches and metas by construction.

| role | old / recent players | pair co-play, old ↔ recent | MMM old | MMM recent | recent: current → corrected on old (move) |
|---|---|---|---|---|---|
| top | 2,520 / 1,840 | +0.30 | +0.20 | +0.28 | +0.28 → **+0.34** (0.06) |
| jungle | 2,992 / 1,797 | +0.32 | +0.19 | +0.32 | +0.32 → **+0.38** (0.05) |
| mid | 1,490 / 1,927 | +0.39 | −0.00 | +0.15 | +0.15 → **+0.32** (0.08) |
| bot | 1,980 / 2,610 | +0.46 | +0.06 | +0.15 | +0.15 → **+0.26** (0.05) |
| support | 1,604 / 2,016 | +0.44 | +0.06 | +0.16 | +0.16 → **+0.29** (0.07) |

The same pairs co-occur across eras more than a year apart (ρ 0.30–0.46,
p 0.001 in every role), and the small label correction learned on the old era
improves agreement on the recent one by 0.06–0.17 with moves of 0.05–0.08.
Both survive a change of meta.

Lower than the EUNE↔EUW replication (0.44–0.67): some of that was shared meta,
so **0.30–0.46 is the meta-free ceiling**. MMM tracks recent pools better than
old ones, plausibly because old pools mix champions from older kits.

Risks: an era split is within the same players, so it tests persistence of
taste and cannot rule out long-lived metas; champions reworked since the old
era are compared under their current labels.
