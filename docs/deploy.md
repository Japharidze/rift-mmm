# Deploying, and loading the data in

One service. The Dockerfile builds the frontend and the API into one image, and
FastAPI serves the build from the same origin — so there is no CORS to
configure, no API base URL that differs between a laptop and the host, and
nothing to change when the host name does.

Nothing secret is needed at runtime. Labels live in the database, so serving
the quiz needs no Anthropic key, and no Riot key either until match data is
being fetched, which happens on a laptop.

## Deploy (dashboard)

1. **New Project → Deploy from GitHub repo →** this repo. Railway sees the
   Dockerfile and uses it; `railway.toml` sets the healthcheck to `/api/games`.
2. **Add a Postgres service** to the same project.
3. **Wire them together.** This is the step that is easy to miss: the app
   service does not get the database URL automatically. In the *app* service's
   variables, add

       DATABASE_URL = ${{Postgres.DATABASE_URL}}

   The reference resolves to the internal hostname
   (`postgres.railway.internal`), which stays inside Railway's network.
4. **Generate a public domain** for the app service.

**Decline the POSTGRES_* variables Railway offers.** It scans the repo, finds
`.env.example`, and suggests importing all five. They are development values --
`POSTGRES_HOST=localhost` means nothing inside a container, and
`POSTGRES_PASSWORD=change-me` is a placeholder. `DATABASE_URL` takes precedence
over them anyway, so importing them changes nothing while the reference
resolves, and makes the failure confusing when it does not. Set `DATABASE_URL`
and nothing else.

`r3m migrate` runs on every boot, so the schema is in place before the first
request. Migrations are idempotent; re-running costs nothing.

## Load the data (no CLI needed)

The dump is not in the image — `.dockerignore` excludes `dumps/`, because the
image should not carry a copy of the database that ages badly. Load it from a
laptop instead, which is the same path a second machine already uses.

1. In the **Postgres** service's variables, copy **`DATABASE_PUBLIC_URL`** —
   the one on `*.proxy.rlwy.net`. Not `DATABASE_URL`: that internal hostname
   only resolves from inside Railway, so it fails from a laptop with a DNS
   error rather than anything informative.
2. Then, locally:

       DATABASE_URL="<the public url>" uv run r3m restore

   `restore` takes the newest file in `dumps/` by default; `--file <path>`
   picks a specific one. Note there are no spaces around the `=`: a shell
   reads `DATABASE_URL = "..."` as a command named DATABASE_URL. The spaced
   form is only for Railway's variable box.

An environment variable takes precedence over `.env`, so this cannot
accidentally aim at localhost — and `r3m.dump._args` hands the URL straight to
psql rather than rebuilding it from the five separate settings, which is what
it used to do and which made exactly that mistake silent.

`restore` refuses a non-empty target, because a data-only dump appends rather
than replaces. To reload later: drop the database, `migrate`, `restore`.

## Between deploying and restoring

The app boots healthy and empty. `/api/games` returns `[]` and the healthcheck
goes green, the grid renders zero cards and the button stays disabled. Not a
crash, but do not share the link until the restore is done.

## Once the panel is running

`quiz_session` rows are guarded in `r3m.dump` alongside the labels, and they are
the one thing in this database that cannot be regenerated: a label can be
re-run for money, and somebody's twenty minutes and their Riot ID cannot be
asked for a second time. Dump the deployment before dropping anything:

    DATABASE_URL="<the public url>" uv run r3m dump

`POST /api/quiz/result` writes a row without authentication, which is fine for
a private link shared with twenty people and not fine if the URL spreads. The
fix when it matters is a shared passphrase in the URL, not accounts.

## Merging `dev` into `main`

Work lands on `dev` and production follows `main`, so a merge is when all of
it reaches the live database at once. In order:

1. **Dump production first -- in full, schema and data.** `quiz_session`
   holds the panel, which cannot be asked for twice, and this dump is also the
   rollback. `r3m dump` alone is not enough for that: it is data-only by design
   (schema comes from migrations), and migrations do not run backwards.

       pg_dump "<the public url>" -Fc --no-owner --no-acl -f data/prod-pre-launch-<date>.dump
       DATABASE_URL="<the public url>" uv run r3m dump

   Into `data/`, which git ignores: it carries the panel's Riot ids, and
   `dumps/` gets committed. Local `pg_dump` must be 18.x like the server.
2. **Merge and let it deploy.** The container runs `r3m migrate` on start and
   applies everything `dev` added (012-019 as of 2026-09-30; 019 adds the
   round-2 replay columns -- events, build, feels_right): 012 drops
   `quiz_session.riot_region`, which the old code still writes -- safe at merge
   time because the new code arrives in the same deploy. During the rollout
   overlap the old container can fail a Riot-id submission for a few seconds;
   harmless with the panel idle.
3. **Import the bank from the laptop:**
   `DATABASE_URL="<the public url>" uv run r3m bank-import`. The image does
   not carry `bank/`, so tiers, parents, bias levels and the new games reach
   production only this way. New games stay out of the quiz until labelled --
   `game_points` only returns labelled games.
4. **Bring the labels over, then choose what is served.** Labels are made
   locally, and a dump/restore would clobber the panel (`restore` refuses a
   non-empty database anyway), so they travel labels-only:

       uv run r3m labels-export --runs <ids> --out dumps/labels-<date>.json
       DATABASE_URL="<the public url>" uv run r3m labels-import dumps/labels-<date>.json
       DATABASE_URL="<the public url>" uv run r3m canonical --champion-runs <new> --game-runs <new>

   Import appends new `label_run` rows with production's own ids -- they are
   not the local ids, which is why the import prints the mapping -- verifies a
   checksum over every score, and skips runs already present, so repeating it
   is safe. Nothing is served until `canonical` names the new ids, and
   `canonical` refuses a set mixing models or effort levels. Migration 017
   flags the validated Opus 5 runs (9 + 10, 17) as served on production, as it
   does locally: checked 2026-09-29, production's runs 9, 10 and 17 are the same
   runs as local (prompt, model and start time identical).
5. **Smoke it:** one quiz through the live site, checking that the row has
   `events`, `build` (with production's new run ids) and `feels_right`.
6. **Optionally store the panel's mains:**
   `DATABASE_URL="<the public url>" uv run r3m panel-check --write`, with a
   fresh Riot development key. Reads `data/panel-mains.json` first, so it
   costs no Riot calls for players already fetched.

## Rolling back the round-2 launch

Recorded before launch, 2026-09-30: production runs **`main` at `5600575`**
(`docs(deploy): restore takes --file, ...`), schema at migration 011. Rollback
is the pre-launch dump plus that commit, in this order -- the order matters,
because the new container runs `r3m migrate` on every start and would re-apply
012-020 onto a restored database:

1. **Redeploy the old build first.** In Railway, redeploy the deployment built
   from `5600575` (or point `main` back at it and let it deploy). Until step 2
   it runs against the migrated schema: results still store, but a Riot-id
   submission fails, because 012 dropped the `riot_region` column it writes.
2. **Restore the pre-launch dump over an emptied schema:**

       psql "<the public url>" -c "drop schema public cascade; create schema public;"
       pg_restore --no-owner --no-acl -d "<the public url>" data/prod-pre-launch-<date>.dump

3. **Check:** `schema_migrations` ends at `011_panel`, `quiz_session` has its
   pre-launch count, and a Riot id submits.

Sessions recorded between launch and rollback are lost unless exported first:
`psql "<the public url>" -c "\copy (select * from quiz_session where build is not null) to 'data/round2-before-rollback.csv' csv header"`.

**Rehearsed 2026-09-30** on a full copy of production restored locally: the
launch sequence (migrate 012-020, bank-import, labels-import twice -- the second
skipped -- canonical refusing a mixed set then serving the new runs, a browser
smoke of both the result and the loved-nothing flows, a dry-run panel-check),
then this rollback -- schema back at 011, 19 sessions, and `5600575` serving a
result and storing a Riot id with its region. No errors.

## Round 2 launched -- 2026-09-30

- **Launch time: 2026-09-30 00:36:23 UTC** -- migrations 012-020 applied on
  production (`schema_migrations.applied_at`); `main` pushed at 00:35:37 to
  `e2633e8`, new API answering at 00:36:26. Round 1 is every session created
  before that instant, round 2 every one after -- the same split as
  `build is null` / `build is not null`.
- **Served from 00:38:52 UTC:** champions `label_run` 23 (v3), games 24
  (games-v2), both `claude-opus-5-5` at high effort -- production's ids for
  local runs 28 and 29. Between 00:36:23 and 00:38:52 the new code served the
  old Opus 5 labels (9 + 10, 17); no session was recorded in that window.
- Pre-launch full dump: `data/prod-pre-launch-2026-09-30.dump` (gitignored,
  holds Riot ids) -- the rollback above uses it.
- Live smoke session (id 20) checked -- build stored runs 24 / 23 and commit
  `e2633e8` -- then deleted. Production held 19 sessions before and after.
- **Fix deployed 2026-09-30 01:27:36 UTC** (`b87827a`): until then the early
  stop ended the quiz after round 1's first 14 cards for nearly everyone
  (found on the first live session, Sergi's own, id 21). Only that session
  saw the short version, and it was deleted; every kept round-2 session has
  all 28 cards.

## Round 2 upgrade -- live 2026-09-30 11:00:34 UTC

The upgraded build (`panel-round-2`: 70 fixed cards in 5 rounds, deep dives,
comparisons before the reveal, drop-off and visit logging) replaces the
28-card build. Same process as the launch above, smaller:

1. **Full dump first**, into `data/` (gitignored):
   `pg_dump "<the public url>" -Fc --no-owner --no-acl -f data/prod-pre-upgrade-<date>.dump`
2. **Merge `dev` into `main`.** The deploy runs migrations 021 (deep_dives),
   022 (outcome `in_progress`, `last_step`, `updated_at`) and 023
   (`page_visit`). The image now also carries `bank/deep_dives.yaml`.
3. **`bank-import` from the laptop** -- the reviewed renown tiers (15
   universal / 40 wide / 15 niche). No labels change: runs 23 and 24 stay
   served, and `canonical` is not touched.
4. **Smoke:** one full quiz on the live site (70 cards, deep dives,
   comparisons, rating), check the row (`build.serving = panel-round-2`,
   `deep_dives`, `last_step = rated`) and one `page_visit` row, then delete
   both.

**Rollback target: `main` at `b87827a`**, the 28-card build, schema at 020.
Same order as above: redeploy `b87827a` first, then restore the pre-upgrade
dump over an emptied schema. Sessions recorded on the upgrade are lost unless
exported first.

**Rehearsed 2026-09-30** on a full copy of production (20 sessions, schema at
020): 021-023 applied cleanly and left the existing sessions untouched;
bank-import applied the reviewed tiers; a full player (70 cards, 5 deep-dive
answers, 3 comparisons), a loved-nothing player who went back and reached a
result, and an abandoned one (in progress at round-3) all stored as intended;
page opens counted; the dry-run panel report showed outcomes split by serving
mode and the drop-off funnel. Then the rollback: schema back at 020, 20
sessions, `b87827a` serving 14-card rounds and storing a result, a Riot id
and a rating with no errors.

**Launched 2026-09-30.** `main` pushed to `9e681b9` at 11:00:04 UTC; migrations
021-023 applied at **11:00:34 UTC** (the upgrade's start: `panel-round-2`
sessions begin here); new API answering at 11:00:44. bank-import applied the
reviewed tiers; runs 23 and 24 still served. Pre-upgrade dump:
`data/prod-pre-upgrade-2026-09-30.dump`.

The live smoke found a bug the rehearsal could not: between steps, a stage
briefly had nothing to show and the page fell back to the last round's card
grid. On local latency it was invisible; on the live site a tap could land on
an old card and change a verdict. Three smoke sessions stopped at it
(in progress at deep / why), and were deleted with their three page visits;
production held 20 sessions and no visits after. Fixed on dev (`c31945f`,
frontend only): a loading screen between steps, verified with 0.8 s of
injected latency on every call.
