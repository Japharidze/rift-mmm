# Co-play families (2026-10-06)

Analysis only: nothing here touches the live quiz. Raw output:
`docs/families-run-2026-10-06.txt`; code `src/r3m/families.py` (`r3m families`,
`r3m families-feasibility`); families saved to `data/families-2026-10-06.json`.

## Step 1: the families

**Method.**
- **Pools:** mid-ladder lifetime pools, the same as `docs/coplay.md`. A champion counts in every role it has a champion×role row for, not only its primary.
- **Affinity:** pair z against a closed-form null that keeps pool sizes and popularity, E = n_a n_b T / S². It matches the curveball z of the co-play experiment (Spearman 0.996 top, 0.994 support), and it is deterministic and fast enough to bootstrap.
- **Number of families (k):** chosen by weighted modularity on the positive-z graph (k 3–10).
- **Consensus:** the same cut is made on 100 resamples of players. Champions are grouped by how often they land together.
  - Firmness is that rate for a member with its family-mates; `?` marks a member below 0.5.
  - Champions with fewer than 30 pools are attached afterwards (`*`).

**Why consensus.**
- A single clustering on one curveball null changed between two runs of the same data: the null shuffles Python sets, whose order varies per process.
- In top, jungle and bot the families moved, so one run is not a result.
- The consensus is identical under different hash seeds.

**How many.**
- Modularity prefers **4 in top, mid and support, 3 in bot, 7 in jungle**.
- The curve is flat from 4 to 7 everywhere (differences ≤ 0.01), so the data does not support 5–8 over 4. It supports "few, broad families".

**Families** (popularity = share of the role's pool slots; canonical MMM centre micro/meso/macro):

| family | pop | range | centre | firm | members |
|---|---|---|---|---|---|
| top-1 | 44% | melee | .36/.41/.53 | .55 | Garen, Teemo, Malphite, Nasus, Kayle?, Shen, Volibear, Mundo, Tryndamere, Cho'Gath, Urgot, Tahm Kench, Yorick, Ornn, Illaoi, Gnar, Trundle, Kled?, Kennen?, Quinn?, Heimerdinger |
| top-2 | 30% | melee | .61/.49/.45 | .59 | Jax?, Vayne, Riven, Irelia, Renekton, Fiora, Camille, Jayce, Cassiopeia?, Gwen, Olaf?, Ambessa, K'Sante, Rumble |
| top-3 | 19% | melee | .52/.46/.37 | .72 | Darius, Mordekaiser, Yone, Sett, Pantheon, Aatrox, Zaahen* |
| top-4 | 8% | melee | .58/.62/.65 | .75 | Gangplank, Sion, Gragas, Singed |
| jungle-1 | 39% | melee | .35/.41/.63 | .45 | Master Yi?, Diana?, Nocturne, Warwick?, Jarvan IV, Amumu, Volibear?, Vi, Xin Zhao, Shyvana, Wukong?, Hecarim?, Zac?, Fiddlesticks?, Rammus?, Sejuani?, Ivern?, Bel'Veth? |
| jungle-2 | 24% | mixed | .58/.56/.70 | .54 | Lee Sin, Kha'Zix, Rengar, Graves, Evelynn?, Elise, Nidalee, Kindred, Rek'Sai? |
| jungle-3 | 19% | melee | .61/.58/.66 | .60 | Kayn?, Ekko, Sylas, Viego?, Talon, Qiyana |
| jungle-4..7 | 3–9% | — | — | .30–.58 | Shaco/Udyr/Quinn/Karthus; Nunu/Zyra/Trundle/Skarner*; Aatrox/Cho'Gath; Briar/Lillia/Naafiri |
| mid-1 | 47% | ranged | .53/.51/.56 | .49 | every mage: Lux?, Ahri, Veigar?, Malzahar?, LeBlanc, Xerath?, Syndra, Vladimir?, Orianna, Viktor, Cassiopeia, Ryze, Anivia, TF?, Lissandra, Kassadin?, Azir, Annie?, ASol?, Mel?, Vex?, Galio, Taliyah? |
| mid-2 | 40% | melee | .72/.61/.53 | .76 | Yasuo, Zed, Katarina, Akali, Yone, Ekko, Sylas |
| mid-3 | 6% | ranged | .70/.56/.50 | .52 | Zoe, Hwei, Qiyana?, Akshan, Naafiri?, Aurora, Locke* |
| mid-4 | 6% | melee | .59/.55/.53 | .55 | Diana, Fizz |
| bot-1 | 79% | ranged | .50/.44/.44 | .81 | Caitlyn, Ezreal, Jhin, Vayne, Kai'Sa, Jinx, MF, Lucian, Ashe, Tristana, Xayah, Sivir, Yunara |
| bot-2 | 11% | ranged | .53/.49/.46 | .62 | Senna, Brand, Veigar, Smolder?, Varus?, Viktor, Ziggs, Corki, Mel |
| bot-3 | 10% | ranged | .61/.41/.45 | .74 | Twitch, Draven, Samira, Aphelios, Kog'Maw, Zeri, Kalista, Nilah |
| support-1 | 35% | melee | .56/.58/.53 | .88 | Thresh, Leona, Blitzcrank, Nautilus, Pyke, Bard, Braum, Rakan, Alistar, Rell, Renata* |
| support-2 | 32% | ranged | .39/.45/.42 | .72 | Nami, Lulu, Janna, Senna?, Zyra, Karma, Soraka, Yuumi, Sona, Milio, Zilean, Taric |
| support-3 | 25% | ranged | .59/.56/.37 | .63 | Lux, Morgana, Brand, Vel'Koz, Seraphine, Neeko |
| support-4 | 8% | melee | .42/.51/.47 | .56 | Swain, Pantheon, Tahm Kench, Poppy, Maokai?, Camille |

**As playstyle groups.**
- **Clear and recognisable:**
  - support: hook/engage, enchanters, mage supports, off-role bruisers;
  - mid: melee assassins against everything else;
  - top: duelists (top-2), juggernauts (top-3), the GP/Sion/Gragas/Singed oddballs;
  - bot: the hypercarry/mechanical group (bot-3) and the mages bot.
- **Not separated:**
  - mid mages are one blob: control and burst are not split;
  - bot-1 is "ordinary marksmen", 79% of the role;
  - top-1 lumps tanks with Teemo/Nasus/Kayle;
  - jungle is the weakest role: a large loose fighters-and-tanks family plus small, soft groups.
- **A release-era trace:** mid-3 (Zoe, Hwei, Akshan, Aurora, Locke) and jungle-7 (Briar, Lillia, Naafiri) are newer champions. Partly "when you started", not taste.

**Stability.** Adjusted Rand index (ARI) between partitions. The null's 95th percentile is 0.05–0.20.

| role | EUNE~EUW | old~recent | EUNE~full | EUW~full |
|---|---|---|---|---|
| top | 0.55 | 0.28 | 0.48 | 0.60 |
| jungle | 0.19 | 0.29 | 0.81 | 0.26 |
| mid | 0.37 | 0.21 | 0.23 | 0.38 |
| bot | 0.14 (null 0.11) | 0.62 | 0.19 | 0.30 |
| support | 0.53 | 0.17 | 0.63 | 0.59 |

- **Moderate** in top and support.
- **Weak** in mid; jungle and bot do not replicate across regions.
- **Old~recent is low almost everywhere:** the families move with time (new champions, meta).

**MMM profile.**
- Families differ mainly in **micro**:
  - top-1 .36 vs top-2 .61;
  - mid-1 .53 vs mid-2 .72;
  - jungle-1 .35 vs jungle-2/3 .58–.61;
  - support-2 .39 vs support-3 .59.
- Meso and macro centres barely differ within a role.
- Spread inside a family (0.11–0.26) is about the size of the distance between centres. Families overlap in MMM.
- Co-play-corrected labels change centres by ≤ 0.06 and tighten spreads by 0.01–0.05. Nothing qualitative changes.

## Step 2: the scoring rule (on paper, not built)

**Inputs.** The current estimator, unchanged, gives the player's point p and an evidence weight w_d per dimension:
- loves: opportunity-weighted, one unit per game;
- dislikes: only on dimensions the game presents;
- deep dives: capped at 0.10;
- comparisons: pull 0.15, cap 0.10.

"Fine" counts toward recognition (the stopping budget), never toward the score.

**Family score (rule A).**
- Each family f has centre μ_f and per-dimension spread s_f, from its members' champion×role labels.
- Over **read dimensions only**, never imputed:

  S_f = −½ Σ_d [ (p_d − μ_fd)² / v_fd + log v_fd ],  where v_fd = s_fd² + σ² / w_d and σ = 0.25.

- The log term stops a wide family winning just by being wide; the first version lacked it.

**Variants measured.**
- **A + popularity:** adds log π_f, the family's share of its role. Using popularity as a prior is a product decision: it leans toward popular champions, which the frozen rule on mains warns about.
- **B:** a kernel per loved or disliked game (width 0.15), so two different loves can each find a family. It ignores deep dives and comparisons.

**Role and stopping.**
- Role score R_r = log Σ_{f in r} exp(S_f).
- Leaders = families within 1.0 (a likelihood ratio of e) of the best.
- **Stop** when the leaders sit in one role, or one primary plus one secondary.
- **Otherwise** ask the game question whose answer best separates the leaders (the hypothesis-testing loop, `docs/quiz-chain.md`).
- **Out of budget:** show the best family plus the best family of another role, labelled as the alternative.

**Inside a family.** Champions are ordered by distance to p; difficulty and price only order the path.

## Step 3: feasibility (n = 5, a sanity check only)

**Who.** Panel players with a result and a Riot id, Sergi excluded, latest session each.
- **True role:** the role with most of their 40 recent games, counting only champions a family holds in that role.
- **True family:** the family in that role holding most of those games. That is 6–13 of 40 games, so the truth itself is thin.
- 22 families in all; a random order puts the true one at rank 11.5 on average.

| rule | mean rank of true family | mean rank of true role (of 5) | true role ranked first |
|---|---|---|---|
| chance | 11.5 | 3.0 | 1/5 |
| A | **14.6** | 3.6 | 0/5 |
| A + popularity | 8.0 | 2.2 | 2/5 |
| B | 11.4 | 4.6 | 0/5 |
| popularity alone | **5.8** | 2.2 | 2/5 |

- **Rule A ranks worse than chance; popularity alone ranks best.**
- **Why A fails:** A sends 4 of 5 players to jungle-2/3 or mid-2, the high-micro, high-macro families. Their quiz points are high on micro and macro, and macro is what separates jungle (Gate 1). So the emergent role is wrong for every one of the five.
- **Why popularity is strong:** with families this unequal (bot-1 holds 79% of bot), it is a strong baseline by construction.

**What a verdict needs.**
- A paired test of the rule's rank against popularity's rank per player (one-sided Wilcoxon).
- **About 50 players** for a moderate effect (d ≈ 0.4), **about 100** for a small one.
- Each player needs a Riot id and at least 10 recent games on champions the families hold in one role.

## Risks

- **Few broad families:** the data supports 3–4 per role, not 5–8; finer families would be noise.
- **Stability:** jungle and bot families do not replicate across regions, and every role drifts between eras.
- **Release era:** some families are "newer champions" (when you started playing), not taste.
- **Lifetime mastery** measures accumulated time, not current taste.
- **MMM overlap:** families separate almost only on micro; meso and macro add little.
- **Popularity:** the families are skewed, so any useful rule must beat a strong popularity baseline. Adding the popularity prior pushes toward popular champions.
- **Emergent role:** rule A's emergent role was wrong for all five panel players, through macro. This is the Gate 1 weakness arriving through families.
- **Feasibility n = 5,** with thin truth (6–13 games): no verdict either way.
- **Segment:** the families come from mid-ladder veterans; newcomers are not in the data.
