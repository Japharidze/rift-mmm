import { useCallback, useEffect, useRef, useState } from "react";

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

const VERDICTS = [
  ["loved", "Loved it"],
  ["meh", "Didn't stick"],
  ["never", "Never played"],
];

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

   An unread dimension shows no marker at all rather than one at its
   provisional value, because a confident-looking position for something we
   cannot yet see is exactly the imputation the model refuses to make. */
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

export default function App() {
  const [stage, setStage] = useState("grid-loved");
  const [grid, setGrid] = useState([]);
  const [loved, setLoved] = useState([]);
  const [disliked, setDisliked] = useState([]);
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

  const fail = useCallback(e => {
    setError(e.message || "Cannot reach the API. Is `r3m serve` running?");
  }, []);

  useEffect(() => {
    get("/quiz/grid").then(setGrid).catch(fail);
  }, [fail]);

  // The running point, for the readout. Cheap, and re-derived from the picks
  // rather than accumulated, so undo and un-tapping are correct for free.
  useEffect(() => {
    post("/quiz/estimate", { loved, disliked })
      .then(r => setDims(r.dimensions))
      .catch(fail);
  }, [loved, disliked, fail]);

  const toggle = (list, setList, id) =>
    setList(list.includes(id) ? list.filter(x => x !== id) : [...list, id]);

  const showResult = useCallback((nextComparisons, nextLoved, nextDisliked) => {
    setBusy(true);
    post("/quiz/result", {
      loved: nextLoved,
      disliked: nextDisliked,
      n: 5,
      comparisons: nextComparisons,
    })
      .then(r => {
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
          loved: nextLoved,
          disliked: nextDisliked,
          comparisons: nextComparisons,
          used: nextComparisons.flatMap(c => [c.winner, c.loser]),
        }).then(p => setPair(p.dimension ? p : null));
      })
      .catch(fail)
      .finally(() => setBusy(false));
  }, [fail]);

  // Stage 2: one card at a time, but only for a dimension the grid left
  // unread, and only while there is one.
  const fillNext = useCallback((nextFills, nextLoved, nextDisliked) => {
    if (!nextLoved.length) { setResult({ empty: true }); setStage("result"); return; }
    setItem(null);
    setBusy(true);
    post("/quiz/fill", {
      served: [...grid.map(g => g.id), ...nextFills.map(f => f.id)],
      loved: nextLoved,
      disliked: nextDisliked,
      asked: nextFills.length,
    })
      .then(r => {
        if (r.item) { setItem(r.item); setStage("fill"); return; }
        return showResult([], nextLoved, nextDisliked);
      })
      .catch(fail)
      .finally(() => setBusy(false));
  }, [grid, showResult, fail]);

  const answerFill = useCallback(verdict => {
    if (!item) return;
    const nextFills = [...fills, { id: item.id, name: item.name, verdict }];
    const nextLoved = verdict === "loved" ? [...loved, item.id] : loved;
    const nextDisliked = verdict === "meh" ? [...disliked, item.id] : disliked;
    setFills(nextFills);
    setLoved(nextLoved);
    setDisliked(nextDisliked);
    fillNext(nextFills, nextLoved, nextDisliked);
  }, [item, fills, loved, disliked, fillNext]);

  const undoFill = useCallback(() => {
    if (!fills.length) return;
    const last = fills[fills.length - 1];
    const nextFills = fills.slice(0, -1);
    const nextLoved = last.verdict === "loved" ? loved.filter(id => id !== last.id) : loved;
    const nextDisliked = last.verdict === "meh" ? disliked.filter(id => id !== last.id) : disliked;
    setFills(nextFills);
    setLoved(nextLoved);
    setDisliked(nextDisliked);
    fillNext(nextFills, nextLoved, nextDisliked);
  }, [fills, loved, disliked, fillNext]);

  const choose = useCallback(winnerIdx => {
    if (!pair) return;
    const [a, b] = pair.pair;
    const [winner, loser] = winnerIdx === 0 ? [a, b] : [b, a];
    const next = [...comparisons,
      { winner: winner.id, loser: loser.id, dimension: pair.dimension }];
    setComparisons(next);
    setPair(null);
    showResult(next, loved, disliked);
  }, [pair, comparisons, loved, disliked, showResult]);

  const restart = () => {
    setError(null); setStage("grid-loved"); setLoved([]); setDisliked([]);
    setFills([]); setItem(null); setResult(null); setComparisons([]); setPair(null);
    setFresh([]); lastKeys.current = null;
  };

  // Keys change how a rapid-fire quiz feels to use. 1/2/3 on a single card,
  // 1/2 on a comparison, backspace to take one back. Held in a ref so the
  // listener is installed once rather than rebound on every answer.
  const keyRef = useRef({});
  keyRef.current = { stage, item, pair, answerFill, choose, undoFill, fills };
  useEffect(() => {
    const onKey = e => {
      const k = keyRef.current;
      if (k.stage === "fill" && k.item) {
        const i = ["1", "2", "3"].indexOf(e.key);
        if (i !== -1) k.answerFill(VERDICTS[i][0]);
        if (e.key === "Backspace" && k.fills.length) k.undoFill();
      }
      if (k.stage === "result" && k.pair) {
        const i = ["1", "2"].indexOf(e.key);
        if (i !== -1) k.choose(i);
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
        <button onClick={restart}>Start again</button>
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
        {VERDICTS.map(([v, text], i) => (
          <button key={v} onClick={() => answerFill(v)} disabled={!item || busy}>
            {text} <span className="key">{i + 1}</span>
          </button>
        ))}
      </main>
    );
  }

  // Stage 1. Two passes over the same cards: what held you, then what didn't.
  // Silence in the second pass is never-played, which is what it already
  // means, so the three-way answer survives the grid intact.
  const meh = stage === "grid-meh";
  const picked = meh ? disliked : loved;
  const cards = meh ? grid.filter(g => !loved.includes(g.id)) : grid;
  return (
    /* Wider than the rest of the app: a 34rem column gives 28 cards three
       across and ten rows of scrolling, which is a list again rather than a
       grid. The point of the grid is that it is taken in at a glance. */
    <main className="wide">
      <h1>{meh ? "Anything here you bounced off?" : "Tap everything you loved"}</h1>
      <Readout dims={dims} />
      <p className="progress">
        {meh
          ? "Games you met and didn't stick with. Skip anything you never played."
          : "Games that held you. Skip the ones you never played."}
        {" · "}{picked.length} picked
      </p>
      <div className="grid">
        {cards.map(g => (
          <button
            className={`gcard ${picked.includes(g.id) ? "picked" : ""}`}
            key={g.id}
            onClick={() => toggle(picked, meh ? setDisliked : setLoved, g.id)}
          >
            <Cover item={g} />
          </button>
        ))}
      </div>
      <div className="actions">
        <button className="next" disabled={!grid.length || busy}
                onClick={() => (meh ? fillNext(fills, loved, disliked) : setStage("grid-meh"))}>
          {meh ? "Done" : "Next"}
        </button>
        {!meh && !loved.length && (
          <button className="link" onClick={() => setStage("grid-meh")}>
            skip — none of these
          </button>
        )}
      </div>
    </main>
  );
}
