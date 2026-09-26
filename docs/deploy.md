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

       DATABASE_URL="<the public url>" uv run r3m restore dumps/<latest>.sql.gz

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
