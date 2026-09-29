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

1. **Dump production first.** `quiz_session` holds the panel, which cannot be
   asked for twice: `DATABASE_URL="<the public url>" uv run r3m dump`.
2. **Merge and let it deploy.** The container runs `r3m migrate` on start and
   applies everything `dev` added (012-016 as of 2026-09-28): 012 drops
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
5. **Optionally store the panel's mains:**
   `DATABASE_URL="<the public url>" uv run r3m panel-check --write`, with a
   fresh Riot development key. Reads `data/panel-mains.json` first, so it
   costs no Riot calls for players already fetched.
