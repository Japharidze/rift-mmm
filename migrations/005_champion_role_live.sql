-- The 30% rule, as something runnable rather than a sentence in CLAUDE.md.
--
-- A role earns its own row when it is how the champion is genuinely played:
-- at least 30% of that champion's games. The threshold is on the secondary
-- share, not the primary, because the primary-share distribution has no natural
-- gap to cut at (measured over 2k ranked solo games, 2026-09-21).
--
-- The second clause is the guard: a champion flat enough that no role clears
-- 30% still keeps its top role, so no champion can end up with zero rows.
-- Enforced here rather than remembered by whoever writes the next query.
--
-- champion_role_share stays threshold-free on purpose: raw shares and the
-- applied rule are different things and should not live in one view. Changing
-- 0.30 needs a migration, which for a frozen decision is the point.

create view champion_role_live as
select champion_id, role, games, champion_games, share
from (
    select
        s.*,
        max(share) over (partition by champion_id) as top_share
    from champion_role_share s
) ranked
where share >= 0.30
   or share = top_share;
