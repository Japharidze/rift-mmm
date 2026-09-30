-- Deep dives (bank/deep_dives.yaml): questions about how someone played a
-- game they loved. Stored like comparisons -- the answers as given, one
-- {question, option} per question put, option null when skipped -- so a
-- replay can re-apply them under any later build, including split answers,
-- which the current build logs without applying.

alter table quiz_session add column deep_dives jsonb;
