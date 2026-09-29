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

// Matches quiz.SHARPEN_MAX. Past three this stops reading as a refinement of
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
function Panel({ sessionId }) {
  const [riot, setRiot] = useState("");
  const [note, setNote] = useState("");
  const [sent, setSent] = useState(false);
  const [failed, setFailed] = useState(false);

  if (!sessionId) return null;
  if (sent) return <p className="note">Thank you — that's genuinely useful.</p>;

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
      <h1>Did it get you right?</h1>
      <p className="gloss">
        If you play League, your Riot ID lets us compare this result against the
        champions you actually play. That comparison is the entire point of
        asking — it is how we find out whether any of this works.
      </p>
      <div className="row">
        <input
          className="field"
          placeholder="Name#TAG"
          value={riot}
          onChange={e => setRiot(e.target.value)}
        />
      </div>
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
      <button onClick={send} disabled={!riot.trim() && !note.trim()}>Send</button>
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
const MAX_ROUNDS = 3;

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
  const [dims, setDims] = useState(null);

  // Stage 2 only. Also the undo stack, which is why it holds names.
  const [fills, setFills] = useState([]);
  const [item, setItem] = useState(null);

  const [result, setResult] = useState(null);
  const [comparisons, setComparisons] = useState([]);
  const [pair, setPair] = useState(null);
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

  // Each step below takes the answers as arguments rather than reading state:
  // they run inside one another's promise callbacks, where state is still the
  // value from before the answer that triggered them.
  const showResult = useCallback((nextComparisons, v, rs, seen) => {
    const { loved: l, disliked: d } = lists(v);
    setBusy(true);
    post("/quiz/result", {
      loved: l,
      disliked: d,
      reasons: rs,
      verdicts: answered(v),
      served: seen,
      n: 5,
      comparisons: nextComparisons,
      session_id: sessionId.current,
    })
      .then(r => {
        sessionId.current = r.session_id ?? null;
        const keys = r.champions.map(c => c.champion_id + c.role);
        const before = lastKeys.current;
        lastKeys.current = keys;
        setFresh(before ? keys.filter(k => !before.includes(k)) : []);
        setResult(r);
        setStage("result");
        // Stage 3 is an offer, so it is fetched alongside the result rather
        // than gating it. No pair means no offer: the result already shown is
        // a complete answer.
        if (nextComparisons.length >= SHARPEN_MAX) return setPair(null);
        return post("/quiz/sharpen", {
          loved: l,
          disliked: d,
          reasons: rs,
          comparisons: nextComparisons,
          used: nextComparisons.flatMap(c => [c.winner, c.loser]),
        }).then(p => setPair(p.dimension ? p : null));
      })
      // Every love was for something other than the gameplay: not an error,
      // a state with its own way forward.
      .catch(e => (/gameplay itself/.test(e.message) ? setStage("nosignal") : fail(e)))
      .finally(() => setBusy(false));
  }, [fail]);

  // Stage 2: one card at a time, only for a dimension still unread.
  const fillNext = useCallback((nextFills, v, rs, seen) => {
    const { loved: l, disliked: d } = lists(v);
    if (!l.length) { setResult({ empty: true }); setStage("result"); return; }
    setItem(null);
    setBusy(true);
    post("/quiz/fill", { served: seen, loved: l, disliked: d, asked: nextFills.length, reasons: rs })
      .then(r => {
        if (r.item) { setItem(r.item); setStage("fill"); return; }
        return showResult([], v, rs, seen);
      })
      .catch(fail)
      .finally(() => setBusy(false));
  }, [showResult, fail]);

  // The follow-ups: one at a time, only where the answer changes the result.
  const startWhy = useCallback((v, rs, asked, seen) => {
    const { loved: l, disliked: d } = lists(v);
    if (!l.length) return fillNext([], v, rs, seen);
    setBusy(true);
    post("/quiz/why", { loved: l, disliked: d, reasons: rs, asked })
      .then(w => {
        if (w.game) { setWhy(w); setStage("why"); return; }
        setWhy(null);
        return fillNext([], v, rs, seen);
      })
      .catch(fail)
      .finally(() => setBusy(false));
  }, [fillNext, fail]);

  // Stage 1: rounds of cards until the server says enough is known.
  const loadRound = useCallback((index, v, rs, seen) => {
    const { loved: l, disliked: d, played: p } = lists(v);
    setBusy(true);
    post("/quiz/round", { index, played: p, loved: l, disliked: d, reasons: rs, served: seen })
      .then(r => {
        if (!r.cards) return startWhy(v, rs, 0, seen);
        setCards(r.cards);
        setRoundIndex(index);
        setServed([...seen, ...r.cards.map(g => g.id)]);
        setStage("round");
        window.scrollTo(0, 0);
      })
      .catch(fail)
      .finally(() => setBusy(false));
  }, [startWhy, fail]);

  useEffect(() => { loadRound(0, {}, {}, []); }, [loadRound]);

  const play = id => setVerdicts(v => ({ ...v, [id]: null }));
  const unplay = id => setVerdicts(v => { const n = { ...v }; delete n[id]; return n; });
  const judge = (id, verdict) => setVerdicts(v => ({ ...v, [id]: verdict }));

  const answerWhy = useCallback(option => {
    if (!why) return;
    const rs = { ...reasons, [why.game.id]: option };
    const asked = whyAsked + 1;
    setReasons(rs);
    setWhyAsked(asked);
    startWhy(verdicts, rs, asked, seenAll);
  }, [why, reasons, whyAsked, verdicts, seenAll, startWhy]);

  const answerFill = useCallback(verdict => {
    if (!item) return;
    const nextFills = [...fills, { id: item.id, name: item.name, verdict }];
    const v = verdict === "never" ? verdicts : { ...verdicts, [item.id]: verdict };
    setFills(nextFills);
    setVerdicts(v);
    fillNext(nextFills, v, reasons, [...served, ...nextFills.map(f => f.id)]);
  }, [item, fills, verdicts, reasons, served, fillNext]);

  const undoFill = useCallback(() => {
    if (!fills.length) return;
    const last = fills[fills.length - 1];
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
    const next = [...comparisons,
      { winner: winner.id, loser: loser.id, dimension: pair.dimension }];
    setComparisons(next);
    setPair(null);
    showResult(next, verdicts, reasons, seenAll);
  }, [pair, comparisons, verdicts, reasons, seenAll, showResult]);

  const restart = () => {
    setError(null); setVerdicts({}); setReasons({}); setWhy(null); setWhyAsked(0);
    setServed([]); setCards([]); setFills([]); setItem(null); setResult(null);
    setComparisons([]); setPair(null); setFresh([]);
    lastKeys.current = null; sessionId.current = null;
    loadRound(0, {}, {}, []);
  };

  // Keys change how a rapid-fire quiz feels to use: numbers on a single card,
  // a follow-up or a comparison, backspace to take a fill answer back. Held in
  // a ref so the listener is installed once rather than rebound on every answer.
  const keyRef = useRef({});
  keyRef.current = { stage, item, why, pair, answerFill, answerWhy, choose, undoFill, fills };
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
      if (k.stage === "result" && k.pair && (n === 0 || n === 1)) k.choose(n);
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

  if (stage === "nosignal") {
    return (
      <main>
        <h1>Nothing to match yet</h1>
        <p>Every game you loved, you loved for something other than how it
        plays — the people, the world, the memories. Those are real reasons,
        but no champion can give them to you, so there is nothing to match on.</p>
        {roundIndex + 1 < MAX_ROUNDS && (
          <button onClick={() => loadRound(roundIndex + 1, verdicts, reasons, seenAll)}
                  disabled={busy}>
            Show me more games
          </button>
        )}
        <button className="link" onClick={restart}>Start again</button>
      </main>
    );
  }

  if (stage === "result" && result) {
    if (result.empty) {
      return (
        <main>
          <h1>Find a champion that fits how you play</h1>
          <p>Nothing you enjoyed, so there's no signal to go on. Say what held
          you, not just what you've touched.</p>
          <button onClick={restart}>Start again</button>
        </main>
      );
    }
    const allDistant = result.champions.every(c => c.confidence === "distant");
    return (
      <main>
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
            {c.because && <div className="gloss">{c.because}</div>}
          </div>
        ))}

        {/* Stage 3. Offered, never imposed: the list above is already the
            answer, and someone who stops here loses nothing. */}
        {pair && (
          <div className="sharpen">
            <h1>Sharpen it</h1>
            <p className="gloss">
              These two differ mostly on {pair.label.toLowerCase()} — {pair.gloss}.
              {" "}{pair.question}
            </p>
            <div className="pair">
              {pair.pair.map((g, i) => (
                <button className="gcard" key={g.id}
                        onClick={() => choose(i)} disabled={busy}>
                  <Cover item={g} />
                  <span className="key">{i + 1}</span>
                </button>
              ))}
            </div>
          </div>
        )}
        {allDistant && (
          <p className="note">
            Nothing lands close. Every League champion carries some of all three,
            so a taste at the edges has no real neighbour — treat these as the
            nearest thing rather than a fit.
          </p>
        )}

        {comparisons.length > 0 && (
          <p className="progress">
            {comparisons.length} comparison{comparisons.length > 1 ? "s" : ""} folded in
          </p>
        )}

        {Object.entries(result.unread).map(([dim, games]) => (
          <p className="note" key={dim}>
            We couldn't tell how you feel about{" "}
            {result.dimensions[dim].label.toLowerCase()}. Played any of these?{" "}
            {games.map(g => g.name).join(", ")}
          </p>
        ))}
        <Panel sessionId={result.session_id} />
        <button onClick={restart}>Start again</button>
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
                onClick={() => loadRound(roundIndex + 1, verdicts, reasons, served)}>
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
