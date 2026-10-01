#!/usr/bin/env bash
# Deploy dev to production in one command, with terse output.
#
#   scripts/deploy.sh            dump, push dev -> main, wait for Railway, API smoke
#   scripts/deploy.sh --bank     ... and r3m bank-import (bank/*.yaml changed)
#
# Forced: no check for players mid-quiz (Sergi, 2026-10-01). Still dumps first,
# because migrations are one-way and the dump is the rollback (docs/deploy.md).
# The smoke is API-only: a browser walk is for UI changes, run separately.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
SITE=https://rift3m.up.railway.app

BANK=0
for a in "$@"; do [ "$a" = "--bank" ] && BANK=1; done

[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "FAIL: uncommitted changes"; exit 1; }
git fetch -q origin
git merge-base --is-ancestor origin/main dev || { echo "FAIL: main is not an ancestor of dev"; exit 1; }
SHA=$(git rev-parse --short dev)
PREV=$(git rev-parse --short origin/main)
[ "$SHA" != "$PREV" ] || { echo "nothing to deploy: main is already $SHA"; exit 0; }

DUMP="data/prod-pre-$SHA-$(date -u +%Y%m%d).dump"
pg_dump "$DATABASE_URL" -Fc --no-owner --no-acl -f "$DUMP"
echo "dump: $DUMP ($(du -h "$DUMP" | cut -f1))"

git push -q origin dev
git fetch -q . dev:main
git push -q origin main
echo "pushed: $PREV -> $SHA at $(date -u +%H:%M:%SZ)"

state=""
for _ in $(seq 1 60); do
  dep=$(gh api "repos/{owner}/{repo}/deployments?per_page=1" --jq '.[0] | "\(.id) \(.sha[0:7])"' 2>/dev/null || true)
  if [ "${dep#* }" = "$SHA" ]; then
    state=$(gh api "repos/{owner}/{repo}/deployments/${dep%% *}/statuses" --jq '.[0].state' 2>/dev/null || true)
    case "$state" in success|failure|error) break;; esac
  fi
  sleep 15
done
[ "$state" = "success" ] || { echo "FAIL: deploy state '${state:-timeout}' -- rollback: redeploy $PREV"; exit 1; }
echo "deployed: $SHA at $(date -u +%H:%M:%SZ)"

if [ "$BANK" = 1 ]; then
  echo "bank: $(uv run r3m bank-import 2>&1 | tail -1)"
fi

games=$(curl -sf "$SITE/api/games" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
cards=$(curl -sf -X POST "$SITE/api/quiz/round" -H 'content-type: application/json' -d '{"index":0}' \
        | python3 -c "import sys,json; print(len(json.load(sys.stdin)['cards']))")
echo "smoke: $games games, deck 1 has $cards cards"
echo "rollback: redeploy $PREV, restore $DUMP if a migration ran"
