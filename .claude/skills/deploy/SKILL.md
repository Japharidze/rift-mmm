---
name: deploy
description: Deploy dev to production (Railway) for rift-mmm. Use when Sergi says deploy, push it live, ship it, or gives the go for a change already committed on dev.
---

# Deploy

Run the script; report its output. Don't re-derive the steps.

```
scripts/deploy.sh            # code-only change
scripts/deploy.sh --bank     # bank/*.yaml changed (tiers, bias, deep dives' bank data)
```

It dumps production (the rollback), pushes dev to main, waits for Railway,
optionally runs `bank-import`, and does an API smoke. Forced: sessions active
in the last 10 minutes print a WARNING line instead of blocking (Sergi,
2026-10-01). Mention the warning when you report.

Before running: everything is committed on dev and the tests passed
(`uv run pytest -q`). Commit first if not.

After running:
- `FAIL` lines: stop and report them; the script prints the rollback target.
- Labels changed (new label runs): the script does not do `labels-import` /
  `canonical`; follow docs/deploy.md for those.
- UI changed: one browser walk on the live site, then delete its session and
  page-visit rows (they are test data). Code-only changes need no walk.
- Add one short entry to docs/deploy.md (commit, what changed, rollback) on dev
  only -- pushing docs to main would redeploy.

Report in a few lines: deployed commit, smoke line, rollback target.
