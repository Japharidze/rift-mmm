# rift-mmm

Maps League of Legends champions and video games into one three-dimensional
space, so a player's taste in games they already know points toward champions
worth trying.

Built for newcomers to League who have a gaming background elsewhere. Existing
champion quizzes ask questions you can only answer after playing League. This
one asks about games you've already played.

## The model

Three dimensions, from Surnex's micro / meso / macro framework:

| | what it demands | the cheat that trivialises it |
| --- | --- | --- |
| **micro** | execution: aim, timing, movement, muscle memory | perfect inputs |
| **meso** | reading people: prediction, deception, habits | knowing the opponent's intent |
| **macro** | systems: routing, resources, win conditions | an engine telling you the right move |

The cheat test is the sharpest diagnostic and the one to reach for first.
`docs/3m-model.md` has the full model and its sources.

**The model is Surnex's; this is an implementation of it, not an extension.**
Three dimensions only — nothing else reaches matching or UI.

Scores are **absolute, 0–1, independent per dimension**. They do not sum to 1.
A champion can be low on all three or high on all three.

## Unit of labelling

One row per **champion × role**, for every role the champion is played in at
least **30% of the time**. Role is part of the vector, not a tag on it — the
same kit in a different lane lands somewhere else, and the role term can
subtract (bot lane removes macro from Ziggs).

The threshold is on the *secondary* share, because the primary-share
distribution has no natural gap to cut at. It lives in
`migrations/005_champion_role_live.sql` as a view rather than in prose, so the
rule is runnable:

```sql
select * from champion_role_live;
```

Measured over 2k ranked solo games: 196 rows across 173 champions, 23 of which
are played in two roles.

## Pipeline

```
Data Dragon  ->  fetch  ->  kit_text  ->  champion, champion_patch
Riot match-v5 ->  sample ->  match, match_participant  ->  champion_role_live
```

| module | job |
| --- | --- |
| `fetch.py` | HTTP: timeouts, retries, backoff, rate limiting. Knows no source. |
| `data_dragon.py` | champion list and per-champion kit entries |
| `riot_api.py` | match-v5 and the ladder endpoints that seed it |
| `kit_text.py` | ability prose, cleaned, for the labelling prompt |
| `sample.py` | resumable match crawl |
| `db.py` | every SQL statement in the project |
| `ingest.py` / `cli.py` | composition and entry point |

Nothing outside `db.py` builds SQL.

## Anchors

`anchors/champions.yaml` holds hand-set MMM scores for a small set of
champions. It is the **regression test**: a labelling run that drifts outside
those bands means the prompt or the model changed, not the game.

Scores are stored as intervals, not points, and each carries a tier —
`tight` blocks a run, `wide` and `provisional` only report. A model-set anchor
cannot test a model, so anything placed by one is never blocking.

## Running it

Requires Docker and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env        # fill in POSTGRES_* and RIOT_API_KEY
docker compose up -d
uv sync

uv run rift-mmm migrate                  # apply schema migrations
uv run rift-mmm ingest                   # load the latest Data Dragon patch
uv run rift-mmm sample --matches 2000    # crawl ranked games (~40 min)
```

`sample` takes a **total**, not an amount to add, and is resumable — an
interrupted crawl keeps everything it stored, and re-running continues from
there. Riot development keys expire every 24 hours.

## Status

Phase 0/1. Champion ingestion, the match sample, and the labelling prompt are
in place. Sub-trait wording is frozen (`docs/sub-traits.md`); a labelling run
needs `ANTHROPIC_API_KEY` and a populated match sample (`champion_role_live`
needs rows before there is anything to label):

```bash
uv run rift-mmm label --champions LeeSin,Garen,Riven   # pilot: anchors only
uv run rift-mmm label                                  # every live champion x role
```

**Gate 1** — does the MMM space contain role information?
**Gate 2** — do synthetic personas land where intuition says?

## Where decisions live

`CLAUDE.md` holds the frozen decisions and the open questions. Read it before
changing anything about labelling, scoring or the unit of work.
