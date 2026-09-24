-- macro_resources: the sub-trait that replaces macro_win_condition for
-- champion labelling from prompt v10 onward.
--
-- Why replace rather than reword. `macro_win_condition` measures scaling, not
-- decision-making. The v8 wording spends six lines excluding exactly that --
-- "a stacking or scaling mechanic is not enough by itself ... farm safely, hit
-- the number, you are strong" -- and Nasus, the archetype of the excluded
-- case, still scores 0.95, the highest of all 196 rows, alongside Kayle,
-- Kassadin, Veigar and Smolder. Negating a pull inside the prompt does not
-- work; docs/sub-traits.md learned the same lesson at v2->v3.
--
-- Three independent sources (Sergi's 25 anchors, 62 podcast-derived anchors, a
-- two-axis difficulty article) all track macro_routing and none track
-- macro_win_condition, so averaging them at equal weight buries routing's
-- signal.
--
-- Resource management is the third term in Surnex's own definition of macro --
-- "routing, resource management, win conditions" -- and the one never
-- decomposed. Adding it completes the definition rather than extending it.
--
-- Both columns are nullable from here: labels are append-only, so runs before
-- v10 carry win_condition and runs from v10 carry resources, and neither
-- rewrites the other.
alter table champion_label
    add column macro_resources numeric(3, 2) check (macro_resources between 0 and 1),
    alter column macro_win_condition drop not null;
