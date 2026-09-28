-- What each panel player actually plays, stored beside the quiz that placed them.
--
-- actual_point (011) is a centroid of those champions, and a centroid was the
-- wrong measure: averaging five or more champions lands near the middle of the
-- space, which is exactly where the "know-nothing" baseline sits, so the
-- baseline won by construction (first run, 2026-09-28). The comparison now
-- measures against each main separately, which needs the list itself.
--
-- Stored rather than re-fetched because development keys expire every 24
-- hours: without this, every re-analysis costs a fresh key and ~45 Riot calls
-- per player. Shape: [{"champion_id": "Ahri", "role": "mid", "games": 12}, ...]

alter table quiz_session add column actual_mains jsonb;
