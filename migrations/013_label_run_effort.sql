-- Effort is a generation setting that moves scores, so it is recorded with the
-- run for the same reason prompt_version and model are (CLAUDE.md,
-- conventions): a re-run that drifts from the anchors has to be attributable.
--
-- Null on every run before this migration. Those calls set no effort, which on
-- claude-opus-5 means adaptive thinking at the model default, `high` -- null
-- means "unset", not "low".

alter table label_run add column effort text;
