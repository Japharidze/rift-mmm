import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const post = async (path, body) => {
  const r = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  // A 4xx body must not land in state as if it were a result — the render
  // then dies on the first missing field and the user sees a blank page.
  if (!r.ok) {
    const detail = await r.json().catch(() => null);
    throw new Error(
      typeof detail?.detail === "string" ? detail.detail : `API ${r.status}`,
    );
  }
  return r.json();
};

const get = async path => {
  const r = await fetch(`/api${path}`);
  if (!r.ok) throw new Error(`API ${r.status}`);
  return r.json();
};

// The three verdicts on a recognised game, in the order they sit on a card.
// "fine" is recognition without taste: it counts toward knowing what someone
// has played and toward nothing else (docs/quiz-chain.md §3). Symbols as well
// as colour, so the choice does not rest on colour vision.
const VERDICTS = [
  ["loved", "Loved it", "♥"],
  ["fine", "Fine", "~"],
  ["disliked", "Didn't like it", "✕"],
];
// The single-card fill stage can also be answered "never played".
const FILL_VERDICTS = [...VERDICTS, ["never", "Never played", "–"]];

const CONFIDENCE = {
  close: "a real match",
  fair: "in the neighbourhood",
  distant: "the nearest thing, not a fit",
};

// Matches quiz.SHARPEN_MAX: comparisons asked before the reveal. Past three this
// stops reading as narrowing it down and starts reading as another round. Was:
// an answer already given and starts reading as a fourth round of questions.
const SHARPEN_MAX = 3;

/* Recognition is the whole mechanism, and a bare title is the weakest cue for
   it: someone who half-remembers a name answers confidently about the wrong
   game. Cover art fixes that where we have it.

   About half the bank has none — Steam does not carry the Nintendo, Blizzard,
   Riot or mobile titles — so a text card is a permanent state, not a loading
   one. It gets its own deliberate treatment rather than an empty image slot:
   an intentionally typographic card reads as a design choice, a blank
   rectangle reads as a bug.

   The year shows on both kinds. Remakes and sequels are exactly where silent
   misrecognition happens, and it is the cheapest thing that separates them. */
function Cover({ item }) {
  const [broken, setBroken] = useState(false);
  // Keyed by id upstream, so state resets with the game rather than leaking a
  // previous card's failure onto the next one.
  const art = item.cover_url && !broken;
  return (
    <>
      {art && (
        <img
          className="art"
          src={item.cover_url}
          alt=""
          /* 28 at once on the grid; only the first rows are ever on screen. */
          loading="lazy"
          onError={() => setBroken(true)}
        />
      )}
      <div className={art ? "caption" : "plate"}>
        <span className="title">{item.name}</span>
        {item.year && <span className="year">{item.year}</span>}
        {!art && item.mode && <span className="genre">{item.mode}</span>}
      </div>
    </>
  );
}

/* Progress as movement rather than a fraction. "N answered" has no
   denominator — the stop condition is adaptive, so there is no honest total —
   and something that visibly settles answers the question the count was
   standing in for: is this going anywhere.

   A marker on an axis, not a filling bar. The three numbers are a *position*
   in a space, not a score out of one: low macro is a taste for games without a
   planning layer, not a deficiency. A bar that grows reads as more-is-better,
   so picking a game you loved could visibly lower all three and look like a
   penalty for answering honestly. A dot that slides has no such implication.

   A dimension still being read is drawn faint, not hidden. Hiding it means
   nothing moves for the first few picks, which reads as broken -- that was
   the first complaint about this component. What CLAUDE.md bars is presenting
   an unread dimension as settled, or substituting the midpoint for it; a
   marker at the actual running mean, visibly provisional and captioned as
   still reading, is neither. The result screen is where the hard line sits:
   there an unread dimension prints "not enough to tell" and no number. */
// Riot ids are GameName#TAG: 3-16 characters, then a 3-5 character tag. Two
// of round 1's three ids came without the tag and had to be guessed.
const RIOT_ID = /^[^#]{3,16}#[A-Za-z0-9]{3,5}$/;

function Panel({ sessionId }) {
  const [riot, setRiot] = useState("");
  const [note, setNote] = useState("");
  const [sent, setSent] = useState(false);
  const [failed, setFailed] = useState(false);

  if (!sessionId) return null;
  if (sent) return <p className="note">Thank you — that's genuinely useful.</p>;

  const riotOk = !riot.trim() || RIOT_ID.test(riot.trim());
  const send = () => {
    post("/panel/details", {
      session_id: sessionId,
      riot_id: riot.trim() || null,
      feedback: note.trim() || null,
    })
      .then(() => setSent(true))
      .catch(() => setFailed(true));
  };

  return (
    <div className="panel">
      <h1>Play League? Add your Riot ID</h1>
      <p className="gloss">
        It is the single most useful thing you can give us: your Riot ID lets us
        compare this result against the champions you actually play. That
        comparison is how we find out whether any of this works.
      </p>
      <div className="row">
        <input
          className="field"
          placeholder="Name#TAG"
          value={riot}
          onChange={e => setRiot(e.target.value)}
        />
      </div>
      {!riotOk && (
        <p className="note">Include the #tag after your name — for example Name#EUNE.</p>
      )}
      <textarea
        className="field wide"
        rows={3}
        placeholder="What did it get wrong? What was confusing?"
        value={note}
        onChange={e => setNote(e.target.value)}
      />
      <p className="gloss small">
        We store your answers, this result, and — if you give it — your Riot ID
        and public match history. Nothing else, no account access, and you can
        leave either field blank.
      </p>
      <button onClick={send} disabled={(!riot.trim() && !note.trim()) || !riotOk}>Send</button>
      {failed && <p className="note">Couldn't send that — the result above is unaffected.</p>}
    </div>
  );
}

function Readout({ dims }) {
  if (!dims) return <div className="readout" />;
  const any = Object.values(dims).some(d => d.informative > 0);
  const settling = Object.values(dims).filter(d => !d.read);
  return (
    <div className="readout">
      {Object.entries(dims).map(([dim, d]) => (
        <div className="bar" key={dim}>
          <span className="bar-label">{d.label}</span>
          <span className={`track ${d.read ? "" : "unread"}`}>
            <span className="tick" />
            {d.informative > 0 && (
              <>
                {/* Anchored at the centre, not the left edge: the length is
                    how decided you are and the side is which way, so nothing
                    here reads as a score going up or down. */}
                <span
                  className="span"
                  style={{
                    left: `${Math.min(50, d.value * 100)}%`,
                    width: `${Math.abs(d.value * 100 - 50)}%`,
                  }}
                />
                <span className="marker" style={{ left: `${d.value * 100}%` }} />
              </>
            )}
          </span>
        </div>
      ))}
      <p className="axis-note">
        {!any
          ? "Pick a few and these will settle."
          : settling.length
            ? `Still reading ${settling.map(d => d.label.toLowerCase()).join(" and ")} — faint until there's enough to be sure.`
            : "Where you sit, not how well you scored — low is a style, not a weakness."}
      </p>
    </div>
  );
}

// Mirrors quiz.MAX_ROUNDS: whether "show me more games" has anything to show.
const MAX_ROUNDS = 5;

const lists = v => ({
  loved: Object.keys(v).filter(g => v[g] === "loved"),
  disliked: Object.keys(v).filter(g => v[g] === "disliked"),
  played: Object.keys(v).filter(g => v[g]),
});
// Verdicts as stored: only answered games, never the null of a pending card.
const answered = v => Object.fromEntries(Object.entries(v).filter(([, x]) => x));

/* One card in a round. Tapping it says "played"; the verdict bar then covers
   its lower part with loved / fine / didn't like and stays for the rest of the
   round, so a choice is changed in place rather than on a later screen.
   Tapping the card above the bar takes it back to not played.

   A card played but not yet given a verdict pulses, and the round cannot move
   on while one does: a silent default ("played, no opinion") is exactly the
   ambiguity this stage exists to remove.

   The whole card is the tap target, but a button cannot contain buttons, so
   the card is a container: a full-size transparent button for played / not
   played, with the verdict segments layered above it. */
function RoundCard({ game, verdict, onPlay, onUnplay, onVerdict }) {
  const played = verdict !== undefined;
  const pending = verdict === null;
  return (
    <div className={`gcard round${played ? " played" : ""}${pending ? " pending" : ""}`}>
      <Cover item={game} />
      <button
        className="hit"
        aria-pressed={played}
        aria-label={played ? `${game.name}: played. Tap to undo.` : `${game.name}: tap if you've played it`}
        onClick={played ? onUnplay : onPlay}
      />
      {played && (
        <div className="vbar" role="group" aria-label={`How did ${game.name} sit with you?`}>
          {VERDICTS.map(([v, text, sym]) => (
            <button
              key={v}
              className={`seg ${v}${verdict === v ? " on" : ""}${verdict && verdict !== v ? " off" : ""}`}
              aria-pressed={verdict === v}
              aria-label={text}
              title={text}
              onClick={() => onVerdict(v)}
            >
              {sym}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [stage, setStage] = useState("round");
  const [roundIndex, setRoundIndex] = useState(0);
  const [cards, setCards] = useState([]);
  // Every round card shown so far; stored with the session.
  const [served, setServed] = useState([]);
  // game id -> "loved" | "fine" | "disliked", or null while a played card
  // waits for its verdict. The one source of truth: the lists derive from it.
  const [verdicts, setVerdicts] = useState({});
  const [reasons, setReasons] = useState({});
  const [why, setWhy] = useState(null);
  const [whyAsked, setWhyAsked] = useState(0);
  // Loves asked about after their round and left unanswered: never asked again.
  const [skipped, setSkipped] = useState([]);
  // The loves of the round just finished, while "what made these stick?" is up.
  const [asking, setAsking] = useState([]);
  const [loveReasons, setLoveReasons] = useState(null);
  // "Do these champions feel right?" -- answered, or skipped, before the
  // reading of the player appears (CLAUDE.md, frozen).
  const [rated, setRated] = useState(null);
  // How a quiz ended without a result: "loved_nothing" or "no_gameplay_love".
  const [outcome, setOutcome] = useState(null);
  const [dims, setDims] = useState(null);

  // Stage 2 only. Also the undo stack, which is why it holds names.
  const [fills, setFills] = useState([]);
  const [item, setItem] = useState(null);

  const [result, setResult] = useState(null);
  const [comparisons, setComparisons] = useState([]);
  const [pair, setPair] = useState(null);
  // Deep dives: the question on screen, and every one put so far.
  const [deepQ, setDeepQ] = useState(null);
  const [deepAnswers, setDeepAnswers] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  // Which champions the last comparison brought in. The cap deliberately keeps
  // stage 3 from relocating the point, so what it does change is usually ranks
  // three to five — a real effect that is invisible unless it is pointed at,
  // and an invisible effect reads as a broken button.
  const [fresh, setFresh] = useState([]);
  const lastKeys = useRef(null);
  // The stored session this quiz belongs to. Sent back with every sharpening
  // re-post so the API updates that row; without it each comparison answered
  // recorded one more session.
  const sessionId = useRef(null);
  // The raw answer log (migration 019): everything shown and answered, in
  // order, so panel round 2 can be replayed against any later estimator.
  const events = useRef([]);
  const started = useRef(Date.now());
  const log = useCallback((type, data = {}) => {
    events.current.push({ t: Date.now() - started.current, type, ...data });
  }, []);

  // Progress writes (migration 022), one after another: the first creates the
  // row, and a second sent before its id came back would create another.
  const stored = useRef(Promise.resolve());
  // Bumped by "start again", so a write still in flight for the old quiz
  // cannot hand its row id to the new one.
  const generation = useRef(0);

  // The top of the funnel (migration 023): once per page load, nothing about
  // the visitor. "Start again" is not a new visit.
  useEffect(() => { post("/visit", {}).catch(() => {}); }, []);

  useEffect(() => {
    get("/quiz/reasons").then(setLoveReasons).catch(() => setLoveReasons(null));
  }, []);

  const { loved, disliked } = useMemo(() => lists(verdicts), [verdicts]);
  const pendingCount = Object.values(verdicts).filter(v => v === null).length;
  const seenAll = [...served, ...fills.map(f => f.id)];

  const fail = useCallback(e => {
    setError(e.message || "Cannot reach the API. Is `r3m serve` running?");
  }, []);

  // The running point, for the readout. Re-derived from the answers rather
  // than accumulated, so changing a verdict or undoing is correct for free.
  useEffect(() => {
    post("/quiz/estimate", { loved, disliked, reasons })
      .then(r => setDims(r.dimensions))
      .catch(fail);
  }, [loved, disliked, reasons, fail]);

  // Nothing to match on. Not a dead end: stored as its own outcome
  // (migration 020) and answered with a way back, never with a guess.
  const endWithout = useCallback((kind, v, rs, seen) => {
    const { loved: l, disliked: d } = lists(v);
    log("outcome", { outcome: kind });
    setOutcome(kind);
    setStage("nothing");
    stored.current = stored.current.then(() => post("/quiz/unresolved", {
      outcome: kind, served: seen, loved: l, disliked: d, verdicts: answered(v),
      reasons: rs, events: events.current, session_id: sessionId.current,
    }))
      .then(r => { sessionId.current = r.session_id ?? sessionId.current; })
      .catch(() => {});
  }, [log]);

  // Each step below takes the answers as arguments rather than reading state:
  // they run inside one another's promise callbacks, where state is still the
  // value from before the answer that triggered them.
  const showResult = useCallback((nextComparisons, v, rs, seen, deep = []) => {
    const { loved: l, disliked: d } = lists(v);
    setBusy(true);
    // After any progress write still in flight, so it carries the row's id.
    stored.current.then(() => post("/quiz/result", {
      loved: l,
      disliked: d,
      reasons: rs,
      verdicts: answered(v),
      served: seen,
      n: 5,
      comparisons: nextComparisons,
      deep_dives: deep,
      session_id: sessionId.current,
      events: [...events.current, { t: Date.now() - started.current, type: "result" }],
    }))
      .then(r => {
        sessionId.current = r.session_id ?? null;
        log("result", { point: r.point, champions: r.champions.map(c => [c.champion_id, c.role]) });
        const keys = r.champions.map(c => c.champion_id + c.role);
        const before = lastKeys.current;
        lastKeys.current = keys;
        setFresh(before ? keys.filter(k => !before.includes(k)) : []);
        setResult(r);
        setStage("result");
        window.scrollTo(0, 0);
      })
      // Every love was for something other than the gameplay: not an error,
      // a state with its own way forward.
      .catch(e => (/gameplay itself/.test(e.message) ? endWithout("no_gameplay_love", v, rs, seen) : fail(e)))
      .finally(() => setBusy(false));
  }, [fail, log, endWithout]);

  // Before the reveal: the player narrowing it down. Up to SHARPEN_MAX pairs,
  // each from games they recognised, each chosen for the axis that would
  // change the answer; none left, or "can't choose", and the result shows.
  const startCompare = useCallback((v, rs, seen, deep, comps) => {
    const { loved: l, disliked: d } = lists(v);
    if (comps.length >= SHARPEN_MAX) return showResult(comps, v, rs, seen, deep);
    setBusy(true);
    post("/quiz/sharpen", {
      loved: l, disliked: d, reasons: rs, comparisons: comps, deep_dives: deep,
      used: comps.flatMap(c => [c.winner, c.loser]),
    })
      .then(p => {
        if (!p.dimension) { setPair(null); return showResult(comps, v, rs, seen, deep); }
        log("pair", { games: p.pair.map(g => g.id), dimension: p.dimension });
        setPair(p);
        setStage("compare");
        window.scrollTo(0, 0);
      })
      .catch(() => showResult(comps, v, rs, seen, deep))
      .finally(() => setBusy(false));
  }, [showResult, log]);

  // Deep dives: how they played the games they loved for the gameplay.
  const startDeep = useCallback((v, rs, seen, deep) => {
    const { loved: l } = lists(v);
    setBusy(true);
    post("/quiz/deep", { loved: l, reasons: rs, answered: deep })
      .then(q => {
        if (!q.question) { setDeepQ(null); return startCompare(v, rs, seen, deep, []); }
        log("deep_asked", { question: q.question });
        setDeepQ(q);
        setStage("deep");
        window.scrollTo(0, 0);
      })
      .catch(() => startCompare(v, rs, seen, deep, []))
      .finally(() => setBusy(false));
  }, [startCompare, log]);

  // Stage 2: one card at a time, only for a dimension still unread.
  const fillNext = useCallback((nextFills, v, rs, seen) => {
    const { loved: l, disliked: d } = lists(v);
    if (!l.length) { endWithout("loved_nothing", v, rs, seen); return; }
    setItem(null);
    setBusy(true);
    post("/quiz/fill", { served: seen, loved: l, disliked: d, asked: nextFills.length, reasons: rs })
      .then(r => {
        if (r.item) { log("fill_shown", { game: r.item.id }); setItem(r.item); setStage("fill"); return; }
        return startDeep(v, rs, seen, []);
      })
      .catch(fail)
      .finally(() => setBusy(false));
  }, [startDeep, fail, log, endWithout]);

  // The follow-ups: one at a time, only where the answer changes the result.
  // Loves were already asked after their round, so these are mostly dislikes.
  const startWhy = useCallback((v, rs, asked, seen, skip) => {
    const { loved: l, disliked: d } = lists(v);
    if (!l.length) return fillNext([], v, rs, seen);
    setBusy(true);
    post("/quiz/why", { loved: l, disliked: d, reasons: rs, asked, skip })
      .then(w => {
        if (w.game) { log("why_asked", { game: w.game.id, kind: w.kind }); setWhy(w); setStage("why"); return; }
        setWhy(null);
        return fillNext([], v, rs, seen);
      })
      .catch(fail)
      .finally(() => setBusy(false));
  }, [fillNext, fail, log]);

  // Stage 1: rounds of cards until the server says enough is known.
  const loadRound = useCallback((index, v, rs, seen, skip = []) => {
    const { loved: l, disliked: d, played: p } = lists(v);
    setBusy(true);
    post("/quiz/round", { index, played: p, loved: l, disliked: d, reasons: rs, served: seen })
      .then(r => {
        if (!r.cards) return startWhy(v, rs, 0, seen, skip);
        log("round", { index, cards: r.cards.map(g => g.id) });
        setCards(r.cards);
        setRoundIndex(index);
        setServed([...seen, ...r.cards.map(g => g.id)]);
        setStage("round");
        window.scrollTo(0, 0);
      })
      .catch(fail)
      .finally(() => setBusy(false));
  }, [startWhy, fail, log]);

  useEffect(() => { loadRound(0, {}, {}, []); }, [loadRound]);

  // Where the session has got to: at the first answer, and at every step
  // after, so someone who gives up mid-quiz still counts (migration 022).
  const step = stage === "round" ? `round-${roundIndex + 1}`
    : stage === "loves" ? `loves-${roundIndex + 1}`
    : stage === "result" ? (rated ? "rated" : "rating")
    : stage;
  const answeredAny = Object.keys(verdicts).length > 0;
  useEffect(() => {
    if (!answeredAny) return;   // nothing is stored before the first answer
    const { loved: l, disliked: d } = lists(verdicts);
    const body = {
      step, served: seenAll, loved: l, disliked: d, verdicts: answered(verdicts),
      reasons, events: events.current, deep_dives: deepAnswers, comparisons,
    };
    const mine = generation.current;
    stored.current = stored.current
      .then(() => post("/quiz/progress", { ...body, session_id: sessionId.current }))
      .then(r => { if (r?.session_id && mine === generation.current) sessionId.current = r.session_id; })
      .catch(() => {});
    // Only on a step change or the first answer: not on every tap.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, answeredAny]);

  const play = id => { log("verdict", { game: id, verdict: "played" }); setVerdicts(v => ({ ...v, [id]: null })); };
  const unplay = id => { log("verdict", { game: id, verdict: "not_played" }); setVerdicts(v => { const n = { ...v }; delete n[id]; return n; }); };
  const judge = (id, verdict) => { log("verdict", { game: id, verdict }); setVerdicts(v => ({ ...v, [id]: verdict })); };

  // After a round: every love in it is asked why, one tap each, skippable --
  // all of them, not only where this build's result would move, so the answers
  // stay usable by any later estimator and the share of loves that are not
  // about the gameplay can be measured (docs/quiz-chain.md §5, §8).
  const endRound = useCallback(() => {
    log("round_end", { index: roundIndex });
    const fresh = cards.filter(g => verdicts[g.id] === "loved" && !reasons[g.id]);
    if (fresh.length && loveReasons) {
      fresh.forEach(g => log("why_asked", { game: g.id, kind: "love" }));
      setAsking(fresh);
      setStage("loves");
      window.scrollTo(0, 0);
      return;
    }
    loadRound(roundIndex + 1, verdicts, reasons, served, skipped);
  }, [cards, verdicts, reasons, served, skipped, roundIndex, loveReasons, loadRound, log]);

  const pickLoveReason = (id, option) => {
    log("why", { game: id, kind: "love", reason: option });
    setReasons(rs => ({ ...rs, [id]: option }));
  };

  const doneLoves = useCallback(() => {
    const left = asking.filter(g => !reasons[g.id]).map(g => g.id);
    left.forEach(g => log("why", { game: g, kind: "love", reason: null }));
    const skip = [...skipped, ...left];
    setSkipped(skip);
    setAsking([]);
    loadRound(roundIndex + 1, verdicts, reasons, served, skip);
  }, [asking, reasons, skipped, roundIndex, verdicts, served, loadRound, log]);

  const answerWhy = useCallback(option => {
    if (!why) return;
    log("why", { game: why.game.id, kind: why.kind, reason: option });
    const rs = { ...reasons, [why.game.id]: option };
    const asked = whyAsked + 1;
    setReasons(rs);
    setWhyAsked(asked);
    startWhy(verdicts, rs, asked, seenAll, skipped);
  }, [why, reasons, whyAsked, verdicts, seenAll, skipped, startWhy, log]);

  const rate = value => {
    log("feels_right", { value });
    setRated(value);
    if (value !== "skipped" && sessionId.current) {
      post("/panel/details", { session_id: sessionId.current, feels_right: value }).catch(() => {});
    }
  };

  const answerFill = useCallback(verdict => {
    if (!item) return;
    log("fill", { game: item.id, verdict });
    const nextFills = [...fills, { id: item.id, name: item.name, verdict }];
    const v = verdict === "never" ? verdicts : { ...verdicts, [item.id]: verdict };
    setFills(nextFills);
    setVerdicts(v);
    fillNext(nextFills, v, reasons, [...served, ...nextFills.map(f => f.id)]);
  }, [item, fills, verdicts, reasons, served, fillNext]);

  const undoFill = useCallback(() => {
    if (!fills.length) return;
    const last = fills[fills.length - 1];
    log("fill_undo", { game: last.id });
    const nextFills = fills.slice(0, -1);
    const v = { ...verdicts };
    delete v[last.id];
    setFills(nextFills);
    setVerdicts(v);
    fillNext(nextFills, v, reasons, [...served, ...nextFills.map(f => f.id)]);
  }, [fills, verdicts, reasons, served, fillNext]);

  const choose = useCallback(winnerIdx => {
    if (!pair) return;
    const [a, b] = pair.pair;
    const [winner, loser] = winnerIdx === 0 ? [a, b] : [b, a];
    log("comparison", { winner: winner.id, loser: loser.id, dimension: pair.dimension });
    const next = [...comparisons,
      { winner: winner.id, loser: loser.id, dimension: pair.dimension }];
    setComparisons(next);
    setPair(null);
    startCompare(verdicts, reasons, seenAll, deepAnswers, next);
  }, [pair, comparisons, verdicts, reasons, seenAll, deepAnswers, startCompare, log]);

  // "Can't choose": no more pairs, straight to the result.
  const noChoice = useCallback(() => {
    if (!pair) return;
    log("comparison", { games: pair.pair.map(g => g.id), winner: null });
    setPair(null);
    showResult(comparisons, verdicts, reasons, seenAll, deepAnswers);
  }, [pair, comparisons, verdicts, reasons, seenAll, deepAnswers, showResult, log]);

  const answerDeep = useCallback(option => {
    if (!deepQ) return;
    log("deep", { question: deepQ.question, option });
    const next = [...deepAnswers, { question: deepQ.question, option }];
    setDeepAnswers(next);
    setDeepQ(null);
    startDeep(verdicts, reasons, seenAll, next);
  }, [deepQ, deepAnswers, verdicts, reasons, seenAll, startDeep, log]);

  const restart = () => {
    setError(null); setVerdicts({}); setReasons({}); setWhy(null); setWhyAsked(0);
    setServed([]); setCards([]); setFills([]); setItem(null); setResult(null);
    setComparisons([]); setPair(null); setFresh([]); setDeepQ(null); setDeepAnswers([]);
    setSkipped([]); setAsking([]); setRated(null); setOutcome(null);
    lastKeys.current = null; sessionId.current = null;
    events.current = []; started.current = Date.now(); stored.current = Promise.resolve();
    generation.current += 1;
    loadRound(0, {}, {}, []);
  };

  // Keys change how a rapid-fire quiz feels to use: numbers on a single card,
  // a follow-up or a comparison, backspace to take a fill answer back. Held in
  // a ref so the listener is installed once rather than rebound on every answer.
  const keyRef = useRef({});
  keyRef.current = { stage, item, why, pair, deepQ, answerFill, answerWhy, answerDeep, choose, undoFill, fills };
  useEffect(() => {
    const onKey = e => {
      const k = keyRef.current;
      const n = Number(e.key) - 1;
      if (k.stage === "fill" && k.item) {
        if (n >= 0 && n < FILL_VERDICTS.length) k.answerFill(FILL_VERDICTS[n][0]);
        if (e.key === "Backspace" && k.fills.length) k.undoFill();
      }
      if (k.stage === "why" && k.why && n >= 0 && n < k.why.options.length) {
        k.answerWhy(k.why.options[n].id);
      }
      if (k.stage === "compare" && k.pair && (n === 0 || n === 1)) k.choose(n);
      if (k.stage === "deep" && k.deepQ && n >= 0 && n < k.deepQ.options.length) {
        k.answerDeep(k.deepQ.options[n].id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (error) {
    return (
      <main>
        <h1>Find a champion that fits how you play</h1>
        <p className="note">{error}</p>
        {/* Resets state rather than reloading, so a hiccup is recoverable. */}
        <button onClick={restart}>Start again</button>
      </main>
    );
  }

  if (stage === "nothing") {
    return (
      <main>
        <h1>Not enough to go on yet</h1>
        {outcome === "no_gameplay_love" ? (
          <p>Every game you loved, you loved for something other than how it
          plays — the people, the world, the memories. Those are real reasons,
          but no champion can give them to you, so there is nothing to match on.</p>
        ) : (
          <p>A match needs at least one game you loved. "Fine" says you know a
          game, not what you enjoy — so if one of them really held you, go back
          and mark it, or see more games.</p>
        )}
        <button onClick={() => { log("back", { index: roundIndex }); setStage("round"); window.scrollTo(0, 0); }}
                disabled={busy || !cards.length}>
          Go back to my answers
        </button>
        {roundIndex + 1 < MAX_ROUNDS && (
          <button onClick={() => loadRound(roundIndex + 1, verdicts, reasons, seenAll, skipped)}
                  disabled={busy}>
            Show me more games
          </button>
        )}
        <button className="link" onClick={restart}>Start again</button>
      </main>
    );
  }

  if (stage === "result" && result) {
    const allDistant = result.champions.every(c => c.confidence === "distant");
    return (
      <main>
        <h1>Champions to try</h1>
        {result.champions.map(c => (
          <div className="champ" key={c.champion_id + c.role}>
            <div>
              <strong>{c.name}</strong> <span className="gloss">{c.role}</span>
              <span className={`tag ${c.confidence}`}>{CONFIDENCE[c.confidence]}</span>
            </div>
            {fresh.includes(c.champion_id + c.role) && (
              <span className="fresh">moved in</span>
            )}
            {rated && c.because && <div className="gloss">{c.because}</div>}
          </div>
        ))}

        {/* Asked about the champions before anything reads the player back to
            them: shown after a reading, the rating measures how flattering the
            reading was instead of the match (CLAUDE.md, frozen; §6.1). */}
        {!rated && (
          <div className="rating">
            <h1>Do these champions feel right?</h1>
            <div className="reasons inline">
              {[["yes", "Yes"], ["partly", "Partly"], ["no", "No"]].map(([v, text]) => (
                <button key={v} onClick={() => rate(v)}>{text}</button>
              ))}
              <button className="link" onClick={() => rate("skipped")}>Skip</button>
            </div>
          </div>
        )}
        {!rated ? null : <>
        <Panel sessionId={result.session_id} />

        <h1>How you play</h1>
        <table><tbody>
          {Object.entries(result.dimensions).map(([dim, d]) => (
            <tr key={dim}>
              <td>
                <strong>{d.label}</strong>
                <div className="gloss">{d.gloss}</div>
              </td>
              <td className="r">{d.read ? d.value.toFixed(2) : "—"}</td>
              <td className="r">{d.read ? "" : "not enough to tell"}</td>
            </tr>
          ))}
        </tbody></table>


        {allDistant && (
          <p className="note">
            Nothing lands close. Every League champion carries some of all three,
            so a taste at the edges has no real neighbour — treat these as the
            nearest thing rather than a fit.
          </p>
        )}

        {Object.entries(result.unread).map(([dim, games]) => (
          <p className="note" key={dim}>
            We couldn't tell how you feel about{" "}
            {result.dimensions[dim].label.toLowerCase()}. Played any of these?{" "}
            {games.map(g => g.name).join(", ")}
          </p>
        ))}
        </>}
        <button onClick={restart}>Start again</button>
      </main>
    );
  }

  // Before the reveal, so no axis is named: "these differ on execution" would
  // tell the player what the answer measures.
  if (stage === "compare" && pair) {
    return (
      <main>
        <p className="progress">Narrowing it down · {comparisons.length + 1} of up to {SHARPEN_MAX}</p>
        <h1>{pair.question}</h1>
        <div className="pair">
          {pair.pair.map((g, i) => (
            <button className="gcard" key={g.id} onClick={() => choose(i)} disabled={busy}>
              <Cover item={g} />
              <span className="key">{i + 1}</span>
            </button>
          ))}
        </div>
        <button className="link" onClick={noChoice} disabled={busy}>Can't choose</button>
      </main>
    );
  }

  if (stage === "deep" && deepQ) {
    return (
      <main>
        <p className="progress">About {deepQ.game}</p>
        <h1>{deepQ.text}</h1>
        <div className="reasons">
          {deepQ.options.map((o, i) => (
            <button key={o.id} onClick={() => answerDeep(o.id)} disabled={busy}>
              {o.label} <span className="key">{i + 1}</span>
            </button>
          ))}
        </div>
        <button className="link" onClick={() => answerDeep(null)} disabled={busy}>Skip</button>
      </main>
    );
  }

  if (stage === "loves" && asking.length && loveReasons) {
    return (
      <main className="wide">
        <h1>{loveReasons.question}</h1>
        <p className="progress">One tap each — or skip any you'd rather not say.</p>
        {asking.map(g => (
          <div className="love-why" key={g.id}>
            <div className="love-name"><strong>{g.name}</strong></div>
            <div className="reasons inline">
              {loveReasons.options.map(o => (
                <button key={o.id}
                        className={reasons[g.id] === o.id ? "on" : reasons[g.id] ? "off" : ""}
                        onClick={() => pickLoveReason(g.id, o.id)}>
                  {o.label}
                </button>
              ))}
            </div>
          </div>
        ))}
        <div className="actions">
          <button className="next" onClick={doneLoves} disabled={busy}>Next</button>
        </div>
      </main>
    );
  }

  if (stage === "why" && why) {
    return (
      <main>
        <h1>Find a champion that fits how you play</h1>
        <Readout dims={dims} />
        <p className="progress">A quick one about {why.game.name}</p>
        <div className="card">
          <Cover key={why.game.id} item={why.game} />
        </div>
        <h1>{why.question}</h1>
        <div className="reasons">
          {why.options.map((o, i) => (
            <button key={o.id} onClick={() => answerWhy(o.id)} disabled={busy}>
              {o.label} <span className="key">{i + 1}</span>
            </button>
          ))}
        </div>
      </main>
    );
  }

  if (stage === "fill") {
    const open = dims && Object.values(dims).find(d => !d.read);
    return (
      <main>
        <h1>Find a champion that fits how you play</h1>
        <Readout dims={dims} />
        {/* The gap is stated rather than hidden, which is what turns this from
            more-of-the-same into a reason the questions are still going. */}
        <p className="progress">
          {open ? `One more on ${open.label.toLowerCase()}` : "One more"}
          {fills.length > 0 && (
            <> · <button className="link" onClick={undoFill}>undo</button></>
          )}
        </p>
        <div className={`card ${item ? "" : "pending"}`}>
          {item && <Cover key={item.id} item={item} />}
        </div>
        {FILL_VERDICTS.map(([v, text], i) => (
          <button key={v} onClick={() => answerFill(v)} disabled={!item || busy}>
            {text} <span className="key">{i + 1}</span>
          </button>
        ))}
      </main>
    );
  }

  // Stage 1: a round of cards. One question per card, "played it?", with the
  // verdict given in place on the card itself.
  const allPlayed = cards.length > 0 && cards.every(g => verdicts[g.id]);
  return (
    /* Wider than the rest of the app: a 34rem column turns a round into a list
       again rather than a grid taken in at a glance. */
    <main className="wide">
      <h1>Which of these have you played?</h1>
      <Readout dims={dims} />
      <p className="progress">
        Round {roundIndex + 1} · tap a game you've played, then how it sat with
        you: ♥ loved it · ~ fine · ✕ didn't like it
      </p>
      <div className="grid">
        {cards.map(g => (
          <RoundCard
            key={g.id}
            game={g}
            verdict={verdicts[g.id]}
            onPlay={() => play(g.id)}
            onUnplay={() => unplay(g.id)}
            onVerdict={v => judge(g.id, v)}
          />
        ))}
      </div>
      <div className="actions">
        <button className="next" disabled={!cards.length || busy || pendingCount > 0}
                onClick={endRound}>
          {allPlayed ? "Next" : "The rest I haven't played"}
        </button>
        {pendingCount > 0 && (
          <span className="progress">
            Say how {pendingCount === 1 ? "that one" : `those ${pendingCount}`} sat with you first
          </span>
        )}
      </div>
    </main>
  );
}
