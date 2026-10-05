-- The blind ranking test (docs/blind-test.md): six champions ranked before
-- the reveal, three from the tester's own result and three yoked from another
-- tester's. One jsonb per session -- cards in display order with source,
-- rank and familiarity, the experience answer, the seed, the yoked session
-- and the distance between the two quiz points. Written only while the
-- session is still in progress, so nobody ranks after seeing their result.

alter table quiz_session add column blind jsonb;
