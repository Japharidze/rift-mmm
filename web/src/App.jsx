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

export default function App() {
  const [answers, setAnswers] = useState([]); // [{id, name, verdict}] — also the undo stack
  const [item, setItem] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const answerRef = useRef(null);

  const idsWhere = (list, verdict) =>
    list.filter(a => a.verdict === verdict).map(a => a.id);

  const advance = useCallback(next => {
    const served = next.map(a => a.id);
    const loved = idsWhere(next, "loved");
    const disliked = idsWhere(next, "meh");
    setItem(null);
    setResult(null);
    post("/quiz/next", { served, loved, disliked })
      .then(r => {
        // A null item means stop: every dimension is read, or the budget is
        // spent. Ending early is intended, not a missing question.
        if (r.item) return setItem(r.item);
        if (!loved.length) return setResult({ empty: true });
        return post("/quiz/result", { loved, disliked, n: 5 }).then(setResult);
      })
      .catch(e => setError(e.message || "Cannot reach the API. Is `r3m serve` running?"));
  }, []);

  useEffect(() => { advance([]); }, [advance]);

  const answer = useCallback(verdict => {
    setAnswers(prev => {
      const next = [...prev, { id: item.id, name: item.name, verdict }];
      advance(next);
      return next;
    });
  }, [item, advance]);
  answerRef.current = answer;

  const undo = () => {
    setAnswers(prev => {
      const next = prev.slice(0, -1);
      advance(next);
      return next;
    });
  };

  const restart = () => { setError(null); setAnswers([]); advance([]); };

  // 1 / 2 / 3 on a rapid-fire quiz changes how it feels to use.
  useEffect(() => {
    const onKey = e => {
      const i = ["1", "2", "3"].indexOf(e.key);
      if (i !== -1 && item) answerRef.current(VERDICTS[i][0]);
      if (e.key === "Backspace" && answers.length) undo();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (error) {
    return (
      <main>
        <h1>Find a champion that fits how you play</h1>
        <p className="note">{error}</p>
        {/* Resets state rather than reloading, so answers survive a hiccup. */}
        <button onClick={restart}>Start again</button>
      </main>
    );
  }

  if (result) {
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
            {c.because && <div className="gloss">{c.because}</div>}
          </div>
        ))}

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
        <button onClick={restart}>Start again</button>
      </main>
    );
  }

  return (
    <main>
      <h1>Find a champion that fits how you play</h1>
      <p className="progress">
        {answers.length} answered
        {answers.length > 0 && <> · <button className="link" onClick={undo}>undo</button></>}
      </p>
      {/* A fixed-height slot, so the question does not jump between rounds. */}
      <p className={`q ${item ? "" : "pending"}`}>{item ? item.name : " "}</p>
      {VERDICTS.map(([v, text], i) => (
        <button key={v} onClick={() => answer(v)} disabled={!item}>
          {text} <span className="key">{i + 1}</span>
        </button>
      ))}
    </main>
  );
}
