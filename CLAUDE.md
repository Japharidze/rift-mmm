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
- **Nine sub-traits**, three per dimension, feed the three aggregates. Each
  dimension's third sub-trait is the cheat test rephrased.
- **Scores are absolute, decimal 0–1 per dimension.** Each dimension is scored
  independently on its own 0–1 scale — they do not and must not sum to 1. A
  champion can be low on all three (0.2 / 0.3 / 0.1) or high on all three
  (0.9 / 0.8 / 0.9).
- **Unit is champion×primary-role.** One row per champion: the role it is most
  played in. Vector = kit + role + environment, so role still shapes the score —
  Karthus-jungle and Karthus-mid would land differently — but only the dominant
  role is labelled. The role term can subtract (bot lane removes macro from
  Ziggs). Keep the schema able to hold several roles per champion even while the
  data holds one, so Gate 1 can add rows back without a migration.
- **Labels are append-only**, grouped by `label_run`. Re-labelling produces a
  diff, never an overwrite. Store sub-traits and aggregates both.
- **Match data does not produce labels.** Its jobs: pick each champion's primary
  role (position distribution), and flag drift for re-labelling
  (win-rate-by-duration, rank-tier spread, deaths).
- **Style first, role second.** Output = MMM point → style neighbourhood → 3–5
  champions labelled by lane → user picks the lane. Result copy: these are first
  picks, the settled lane comes later.
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

## Stack

Python, PostgreSQL. Data is small — no Spark, no warehouse, no dbt. Python is
the whole transformation layer; plain SQL views cover the rest.
React frontend, same repo under /web.

## Current phase

Phase 0/1: schema + Data Dragon ingestion, then the labelling prompt.

**Gate 1** (after champion labelling): does the MMM space contain role
information — can role be predicted from the three coordinates better than
chance? High → role comes free. Moderate → present style neighbourhood across
roles (expected). Near-zero → add one explicit role question. If clustering is
incoherent: fall back to role×subclass priors blended with whatever structure
emerged. One day, not a restart.

**Gate 2** (after scoring engine): do synthetic personas and dry runs land where
intuition says? Go → build MVP.

## Open questions — discuss, don't decide in code

- Sub-trait wording. The main risk to label quality. Freeze before mass
  labelling; never edit mid-run.
- Weights: equal for the pilot, then fit against the games Surnex placed himself
  (see `docs/3m-model.md`); factor-check the nine afterwards.
- Riot production key: apply early; design the MVP to run on cached data so
  launch never blocks on approval.
