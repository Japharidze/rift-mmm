# Blind ranking test with yoked controls — design (2026-10-05)

**Question:** does the quiz personalise? Do testers prefer the champions the
quiz picked *for them* over champions it picked for someone different?
"Quiz picks vs random" would only test whether the quiz's champions are
generally appealing -- and the quiz gives nearly everyone similar champions.

Runs on the current build. Nothing about how answers become results changes;
one screen is added before the reveal.

## Flow

1. The quiz runs as now, up to the moment the result would show.
2. **Before the reveal**, one screen:
   - "How much League have you played?" -- *never* / *a few games* /
     *regularly*. Asked once, before the six cards.
   - **Six champion cards, ranked 1–6** ("which would you most like to try?")
     by tapping in order. Per card, prior familiarity: *played it* /
     *heard of it* / *new to me*.
3. Then the result shows as now. A tester who has seen their result never
   ranks: the order is enforced by the API, not only the page.

## The six champions

- **Own:** the tester's top 3 from their own result.
- **Yoked:** the top 3 from **another tester's** stored result, chosen as the
  completed session whose quiz point is **farthest** from this tester's
  (required at least 0.15 away; if none is, the farthest available, and the
  distance is logged). Any champion in both sets is replaced by that other
  tester's next-ranked champion, until the sets are disjoint.
- The first testers are yoked to stored sessions (round 1 and round 2, Sergi's
  own excluded), so nobody waits for a partner.

## Identical presentation

Same card for all six: the champion's square portrait (Data Dragon), the
name, and **one neutral line about the kit**. No MMM words, no labels, no
lane, no "fits you", no confidence tag. Order randomised per tester (seeded,
logged).

**Open point -- the neutral kit line needs a source.** Riot's title and blurb
are lore; its tags are exactly the labels the test must not show. Options:
(a) I write 173 one-line kit descriptions (no MMM words, no class names; no
API spend) and you spot-check them; (b) no line at all, portrait and name
only. (a) fits the brief; (b) is simplest and identical for all six.

## Logged

Per tester: the experience answer, the six champions with their source (own
or yoked) and the tester's rank for each, familiarity per champion, display
order, the yoked session's id and the distance between the two quiz points --
in the session's event log and a column of its own.

## Decision rule (fixed now, before any data)

Per tester: **d = mean rank of yoked picks − mean rank of own picks**
(positive means own picks preferred; d ranges from −3 to +3).

- **Primary:** testers who answered *never* or *a few games* (the segment).
- **Pass:** among at least **20** such testers, a one-sided Wilcoxon signed-
  rank test on d gives **p < 0.05**, **and** mean d is **at least +0.5**
  (own picks average half a rank higher). Both conditions are required.
- **Fail:** either condition missed at n ≥ 20. Below 20 primary testers there
  is no verdict.
- **Robustness, reported but not deciding:** the same test excluding
  champions marked *played it* (familiarity is ranked up regardless of fit);
  veterans (*regularly*) separately; d against the yoked distance.

## Risks

- Quiz points cluster, so "farthest" may still be near; the logged distance
  shows how much contrast each tester actually got.
- The experience answer is self-reported.
- Portraits carry appeal of their own; randomised order spreads it evenly over
  own and yoked, it does not remove it.
