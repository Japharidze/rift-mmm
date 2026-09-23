# rift-mmm

Maps League of Legends champions and video games into one three-dimensional
space (micro / meso / macro), so a player's taste in games they already know
points toward champions worth trying.

Segment: newcomers to League who have gaming background elsewhere. Existing
champion quizzes (e.g. whotoplay.gg) ask questions you can only answer after
playing League — this one asks about games you've already played.

Read `docs/3m-model.md` before working on anything in `labeling/`.

## Attribution

The micro/meso/macro model is Surnex's. This is an implementation of it, not an
extension. Keep it that way: three dimensions only, nothing else surfaces in
matching or UI.

## Frozen decisions — do not relitigate in code

- **Three dimensions only.** micro, meso, macro. Other traits (risk, carry,
  tempo, difficulty) may exist as labelling inputs, never as matching dimensions
  or UI concepts.
- **Riot's class tags are never a labelling input.** Mage, Fighter, Assassin,
  Tank, Support, Marksman are stored from Data Dragon for validation only and
  never rendered into the prompt. MMM is derived from kit and role; handing the
  labeller an existing taxonomy anchors it to that taxonomy instead of to the
  three dimensions.
- **Sub-traits feed the three aggregates, at least three per dimension.**
  Three is the floor: a factor with fewer indicators cannot be estimated. But
  with exactly three the single-factor model is just-identified — fit is perfect
  by construction and untestable — so four is where per-dimension fit can
  actually be checked. Starting allocation is **3 / 4 / 3**, the extra on meso,
  which is the hardest dimension to read from a kit and therefore has the
  noisiest individual indicators. The count is an output of the pilot, not an
  input: the factor check and run-to-run disagreement decide whether it holds.
  The **last** sub-trait in each group is the cheat test rephrased. Wording is
  frozen in `docs/sub-traits.md` — that file is the source of truth, not this
  bullet.
- **Scores are absolute, decimal 0–1 per dimension.** Each dimension is scored
  independently on its own 0–1 scale — they do not and must not sum to 1. A
  champion can be low on all three (0.2 / 0.3 / 0.1) or high on all three
  (0.9 / 0.8 / 0.9).
- **Unit is champion×role, one row per role played in at least 30% of games.**
  Vector = kit + role + environment, so role shapes the score — Karthus-jungle
  and Karthus-mid land differently. The role term can subtract (bot lane removes
  macro from Ziggs). The threshold is on the *secondary* share, not the primary:
  the primary-share distribution has no natural gap to cut at, whereas "played
  in 30% of games" says a role is genuinely how the champion is played whatever
  the rest of the split does. Measured 2026-09-22 over 2,060 ranked solo games:
  196 rows across 173 champions — 23 get a second row, none a third. A champion
  flat enough that no role clears 30% must still keep its top role.
- **Labels are append-only**, grouped by `label_run`. Re-labelling produces a
  diff, never an overwrite. Store sub-traits and aggregates both.
- **Match data does not produce labels.** Its jobs: decide which roles each
  champion is played in (position distribution against the 30% threshold), and
  flag drift for re-labelling (win-rate-by-duration, rank-tier spread, deaths).
  For drift, weight recent patches more heavily rather than filtering to them: a
  champion that changed lanes months ago still carries the old lane in a flat
  average.
- **Style first, role second.** Output = MMM point → style neighbourhood → 3–5
  champions labelled by lane → user picks the lane. Result copy: these are first
  picks, the settled lane comes later.
- **A dimension the quiz could not read is reported, never imputed.** If a user
  picks no games that load on a dimension, recommend from the two that were
  measured and say the third is open — then offer a short second round serving
  only items loaded on the missing one. Filling the gap with the midpoint is how
  confident nonsense ships, and the honest version is a retry hook rather than
  an apology. The champion side has the same requirement arriving from the other
  direction: a match 0.45 away must not be presented like one 0.04 away
  (Gate 2, limitations).
- **No agent framework for labelling.** Plain loop, versioned system prompt,
  structured output, retries.
- **Never use the abbreviation "KYS"** anywhere — toxic meaning in gaming. Check
  any new abbreviation against gaming slang before committing.

## Conventions

- Labelling code never touches the DB directly — go through `db.py`.
- The system prompt is a versioned constant; every label row records the prompt
  version and model that produced it.
- Anchor scores are a repo fixture (`anchors/champions.yaml`), not DB data. They
  are the regression test: a re-run that drifts from anchors means the prompt or
  model changed, not the game.

## Commit style

Conventional Commits, subject line only — no body, no footer beyond required
attribution. Observed across the existing history, not aspirational:

- `type(scope): subject` — `feat(sample): match-v5 crawl and participant
  metrics`, `refactor(fetch): remove unnecessary cache managemenet`,
  `docs: readme; role threshold and sub-trait count`.
- Types seen: `feat`, `refactor`, `docs`. `fix` follows the same shape when it
  comes up.
- Scope is the module or area touched (`fetch`, `sample`, `roles`,
  `ingestion`) — the file/dir name if there's an obvious one, not a category
  invented for the commit. Omit it when the commit spans areas rather than
  living in one (`feat: anchors added`, `feat: data_dragon; db`).
- One subject line, lowercase, no trailing period. Semicolons join more than
  one thing in that single line rather than spilling into a body
  (`feat(fetch): rate limiting; honour Retry-After in full`).
- Phrase it however reads clearest — imperative isn't required
  (`feat(ingestion): done for champions` is a real commit here).

## Stack

Python, PostgreSQL. Data is small — no Spark, no warehouse, no dbt. Python is
the whole transformation layer; plain SQL views cover the rest.
React frontend, same repo under /web.

## Current phase

Phase 2: both gates passed, building the MVP. The next blocker is the game
side — nothing yet turns "I played Factorio and Hearthstone" into an MMM point,
so there is no games table and no `anchors/games.yaml`.

Phase 1 done: schema, Data Dragon ingestion, the match sample, `champion_role`,
and the first full labelling pass — 196 champion×role rows at prompt v3
(`label_run` 9 and 10; 10 fills 8 rows lost to network errors, so the complete
set is the two unioned, preferring the later row per champion×role). Next is the
scoring engine, toward Gate 2.

**Gate 1 — passed 2026-09-22, Moderate.** Can role be predicted from the three
coordinates better than chance? Measured by leave-one-out k-NN over all 196
rows, chosen because it is the product's own mechanism rather than a convenient
classifier: if role falls out of a style neighbourhood, role comes free.

- **40.8%** at k=15 and **32.1%** at k=1, against a 23.5% majority-class
  baseline and 20% chance. Real signal, well short of free. Accuracy rising
  with k means it reads broad regional base rates, not tight neighbourhoods, so
  32% is the honest neighbourhood number.
- **Separation ratio 0.73** — champions sit further from their own role's
  centroid than the centroids sit from each other. Roles overlap; they do not
  cluster.
- Nearly all of it is jungle (80% recall) and nearly all of it is macro
  (centroid spread 0.24, against micro 0.12 and meso 0.10). **Top lane scores
  15%, below chance** — it is the most average point in the space, and a
  top-inclined user will get the least lane information from their
  neighbourhood.
- **The role term works.** Across the 23 two-role champions, changing only the
  role moves the vector 0.120, against 0.350 for two random rows. Macro moves
  0.094 and always in the right direction (top→jungle raises it, →support
  lowers it); micro moves 0.029, which is the noise floor, so micro correctly
  ignores role. Karthus-jungle and Karthus-mid do land differently, for the
  right reason.

Decision: the expected branch. Style neighbourhood across roles, champions
labelled by lane, user picks. No explicit role question, and no fallback to
role×subclass priors.

**Gate 2 — passed 2026-09-22.** Do synthetic personas and dry runs land where
intuition says? Seven personas, each an MMM point taken from Surnex's own game
placements in `docs/3m-model.md` rather than invented, matched against the 196
labelled champion×role rows:

- Hearthstone / TFT (meso+macro) → Singed, Evelynn, Shaco, Teemo, Fiddlesticks
  — the deception and setup champions, reached with no notion of "deception"
  anywhere in the pipeline.
- Among Us (pure meso) → Blitzcrank. Factorio (pure macro) → Nasus.
  osu! (pure micro) → Draven. CS2 (all three) → Lee Sin.

Every persona spans two or three lanes, which is the Gate 1 branch behaving as
designed. Go → build MVP.

Three limitations carried into the MVP rather than resolved:

- **The champion cloud does not reach the corners.** Nothing sits below ~0.2 on
  any axis, and four of the eight corners have no champion within 0.30 — worst
  for pure micro (0.45) and pure meso (0.47). A pure-anything taste gets a
  nearest match that is ranked first but is not close. **The result UI has to
  express confidence, not just order**, or it will present a 0.45 match exactly
  as it presents a 0.04 one.
- **Macro is load-bearing and the least verified axis.** Removing it leaves
  1.4/5 recommendations standing and collapses the CS2 and Street Fighter
  personas onto one identical list, so it can be neither dropped nor
  down-weighted. Yet its correlation with the anchors sits somewhere in
  [0.05, 0.77] across 19 tight anchors. The product leans hardest on the
  dimension measured worst; closing that needs more anchors, not more prompting
  (see `docs/sub-traits.md`, v4–v6).
- **Meso is the narrowest dimension** (sd 0.13 against micro's 0.18), and two
  prompt versions failed to widen it. Expect it to separate less than the
  other two.

## Open questions — discuss, don't decide in code

- Weights: equal for the pilot, then fit against the games Surnex placed himself
  (see `docs/3m-model.md`); factor-check the sub-traits afterwards.
- Riot production key: apply early; design the MVP to run on cached data so
  launch never blocks on approval.
