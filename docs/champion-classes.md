# Champion classes and the skills they demand

Distilled from We Teach League / Broken by Concept, *"best champions to learn
each class for every role"* — the Mid, Jungle and Bot academy coaches, with top
lane relayed from Chippies. Transcript supplied 2026-09-22 and stored at
`docs/transcripts/02-champion-classes.md` (40 chapters, 3h45m).

Chapter 8, *Mid: Enchanters*, has no entry below because the coaches conclude
the class is not viable mid any more and recommend nobody. Everything else in
the transcript appears here.

Each class names a **purist** (embodies the class at its extreme) and a
**recommended** (teaches the same skills but actually gets results).

## How to use it

**For anchors, not for the prompt.**

Anchors need extremes, and a purist is an extreme by construction. This is also
a second opinion independent of both the labeller and the anchor author — which
matters, because one Emerald player's judgment can settle a gross error but not
a disagreement.

Do **not** put these subclass names in the labelling prompt. CLAUDE.md bars
Riot's class tags because "handing the labeller an existing taxonomy anchors it
to that taxonomy instead of to the three dimensions." That reasoning is about
taxonomies, not about Riot — and this one would anchor harder, being sharper.

## Reading the skills as MMM

- **micro** — precision, spacing and tethering, combos, skillshot reliance.
- **meso** — fog usage, threat, bluffing, when to show yourself, reading *this*
  opponent, "occupying the enemy's mental stack".
- **macro** — wincon assessment, tempo, resets, routing, wave states,
  deployments, objective timing, saying no, translating leads.

When a class is called *cerebral* or *big-brain*, that is almost always macro.

## Mid

- **Lane bully mages** — Zoe / Viktor. Lane fundamentals, tempo, resets; patience over aggression.
- **Scaling mages** — Aurelion Sol, Vladimir / Syndra. Saying no; knowing your spikes; summoner intentionality.
- **Mobile mages** — Ahri / Ahri. Mobility as a tool to create advantage, not as an escape.
- **AP assassins** — Akali / Ekko. Fog; deciding *when to show yourself*; precise target selection.
- **AD assassins** — Qiyana / Naafiri. As above, plus: must impose threat even to farm.
- **Utility** — Twisted Fate / Galio, Anivia. Wincon thinking; at least one spell that does no damage.
- **Roamers** — Talon / Taliyah. Wave states, tempo, wincon assessment. Wave clear is the prerequisite.
- **Hyperscalers** — Kayle / Kassadin. Expert at saying no; disciplined to the point of delusion.
- **Fighters** — Yone / Yasuo. Mechanics max; knowing when strong and weak; poor at translating leads.

## Jungle

- **Carry fighters** — Viego / Wukong (Shyvana evergreen). Opportunistic, can't force; must reach three items.
- **Team-oriented fighters** — Vi / Nocturne. Early presence; can only kill one target; sets up carries.
- **Hyperscalers** — Karthus / Master Yi. Selfish; camp tempo; stem the bleeding; execute fights at three items.
- **ADC junglers** — Kindred, Graves. All-rounder; Graves must close the game out.
- **Assassins** — Kha'Zix / Talon. Picks not teamfights; high- vs low-value kills; **create your own fog**.
- **AP outcasts** — Lillia / Fiddlesticks. No shared skill set — this is "I need an AP pick".
- **Carry tanks** — Amumu / Zac. Needs items; provides CC but can kill; easy clears free up mental stack.
- **Utility tanks** — Ivern / Skarner. Purely playing the map; single target; cannot kill alone.
- **Mages** — Taliyah / Zyra. Camp tempo; front-to-back positioning, which is rare for junglers.

## Top

- **Bruisers** — Renekton / Olaf. A ticking clock: win lane, then **translate the lead** before you fall off.
- **Juggernauts** — Sett (Garen). Closing the gap with no mobility; extended trades; still show up for neutrals.
- **Fighter / skirmishers** — Jax. Mechanically demanding; options in the mid game; brutal once behind.
- **Splitpushers** — Trundle (Fiora advanced). Sinking pressure; timing it to the team; high-value deaths.
- **Tanks** — Sion (Malphite). Strong *short* trades; outscaled in side lane, so group and force fights.
- **Ranged tops** — Kayle. Spacing and tethering; conserve HP; small wins; unforgiving when behind.

## ADC

- **Lane bullies** — Draven / Miss Fortune. Early strength exists to get *all the farm*, not only to fight.
- **Hyperscalers** — Smolder / Sivir. Survive lane, say no, pump economy; influence comes from teamfights.
- **Utility** — *(no purist — an ADC's directive is damage)* / Jhin. Mid-game picks via non-committal engage.
- **Mage bot laners** — Ziggs / Hwei, Seraphine. Anti-ADC: pin them under tower. Ability usage ADCs lack.

## Support

- **Battle enchanters** — Karma / Nami. Proactive trading; pressure the enemy ADC without dying to ganks.
- **Scaling enchanters** — Yuumi / Sona. *Should* play like battle enchanters; above Emerald you must.
- **Mages** — Xerath / Zyra (Neeko high skill cap). Must win lane; gold-reliant; miss and you are nothing.
- **Engagers** — Rell / Leona. Roaming; linking with the jungler; limit testing; engage quality and timing.
- **Playmakers** — Pyke / Thresh (Bard, Blitzcrank). The most cerebral, highest ceiling: wincon, tempo, fog,
  picks, and **occupying the enemy's mental stack** — "if they aren't worried about you, you aren't a champion".
- **Fighter supports** — Camille / Pantheon. Must snowball; knowing limits; making the game chaotic.

## Four things worth keeping

1. **A class name means different things per role.** Mid assassins kill in front
   of a team; jungle assassins need isolation. A role-blind label collapses these.
2. **"Purest" means extreme, not good.** Zoe is purest because she has no
   fallback; Katarina roams but is too forgiving to qualify. Anchors want exactly
   that property.
3. **Wave clear is named as the prerequisite for map agency.** Talon and Katarina
   roam because they can shove first — a kit-level macro signal.
4. **Playmaker supports are called the highest skill ceiling in the game.**
   Blitzcrank is in that group. The model scores him 0.33 macro.

## What the 62 placements measured, 2026-09-24

All 62 candidates placed (26 `tight`, 36 `wide`), then compared against v3.
Mean error and band rate matched the existing 25 anchors closely (0.142 vs
0.138, 55% vs 51% inside band), but correlation split sharply by dimension once
corrected for restricted range -- the bucket vocabulary spans [0.20, 0.75],
against the existing set's 0.12-0.90, which attenuates correlation mechanically:

    dimension   raw   range-corrected   existing 25
    micro       0.50       0.70            0.84
    meso        0.37       0.56            0.74
    macro       0.02       0.03            0.53

**Micro and meso are usable. Macro is not**, and the reason is structural
rather than a matter of judgment. Comparing variation within a class against
variation between classes:

    dimension   within   between   ratio
    micro        0.087    0.102     0.85
    meso         0.068    0.088     0.78
    macro        0.055    0.114     0.48

For micro and meso the placements vary substantially within a class -- Yasuo
and Yone are both Fighters and were scored differently, because champion
knowledge was applied on top of the class line. For macro they largely track
the class line itself.

So this source yields a **class-level** macro judgment, while the labeller
scores a **per-champion** kit. Kayle and Kassadin are both Hyperscalers with
very different kits. Zero correlation is what two different objects look like,
not what a bad anchor looks like.

There may also be a vocabulary mismatch underneath: the coaches' macro language
("wincon assessment", "saying no", "tempo") describes what the *player* does in
a role, while the labelling prompt asks what the *kit* demands. Those can come
apart.

Consequence: merge micro and meso from this set, which roughly triples the
anchored dimensions on both. Keep macro out of the blocking set. Macro still
lacks an independent per-champion source -- which remains the oldest open
problem in the project (Gate 2, and four reverted `macro_routing` rewrites).

## The role term, corroborated — 2026-09-24

A second Broken by Concept episode ("the skills each role needs to climb")
describes what each of the five roles demands, role by role. Useless as
champion anchors -- it compares roles, not champions -- but the unit here is
champion x role and CLAUDE.md has the vector as kit + role + environment, so
this is a direct external account of the role term. Gate 1 could only validate
that term internally, by showing role swaps move a vector consistently.

Measured over the 196 v3 rows:

    role        n   micro   meso   macro
    top        46    0.57   0.53    0.54
    jungle     46    0.57   0.56    0.69
    mid        39    0.69   0.63    0.52
    bot        30    0.68   0.54    0.46
    support    35    0.59   0.60    0.45

Against what the coaches say:

- **"Win condition assessment"** is named the jungler's first mid-game skill.
  Jungle macro is 0.69 against 0.54 for the next role -- a 0.15 gap, the
  largest single role effect in the data.
- **"The macro for AD carry is not complex, the fighting is complex"**, and
  "you don't win games through creative macro, lane assignments, ganks, tempo,
  invades". Bot macro 0.46, micro 0.68.
- **"Top is so much more stat checky than mid"**. Top has the lowest micro of
  any role.
- **Support is "a very cerebral role"** where "you're operating in the currency
  of mental stack" and trying to "overwhelm their mental stack". Support is
  second on meso.

One disagreement, kept rather than resolved: support macro is the lowest of any
role (0.45), while the episode lists win-condition assessment as support's
second mid-game skill. The transcript's own vocabulary for what makes support
cerebral -- mental stack, being annoying, baiting hooks, wasting time -- is
meso rather than macro, so the two may be describing different things with one
word. Testable once there are support anchors.

This corroborates the role term. It says nothing about telling champions apart
within a role, which is where the measurement problem actually lives.
