import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../lib/api";
import WaveDivider from "../components/WaveDivider";

export default function GamePlay() {
  const { sessionId } = useParams();
  const [round, setRound] = useState(null);
  const [result, setResult] = useState(null);
  const [finished, setFinished] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  async function loadRound() {
    setLoading(true);
    setResult(null);
    try {
      const r = await api.get(`/games/sessions/${sessionId}/round`);
      setRound(r);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadRound();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  async function answer(option) {
    setError(null);
    try {
      const r = await api.post(`/games/sessions/${sessionId}/answer`, { answer: option });
      setResult(r);
      if (r.session_status === "completed") {
        setFinished(true);
      } else {
        setTimeout(loadRound, 900);
      }
    } catch (e) {
      setError(e.message);
    }
  }

  if (loading && !round) return <WaveDivider animated />;
  if (error) return <div className="alert alert-danger">{error}</div>;

  if (finished && result) {
    return (
      <div className="stack">
        <div className="card stack">
          <h2>Round complete!</h2>
          <p>
            You scored <strong>{result.score}</strong> points, with {result.correct_count} of {result.total_rounds} correct.
          </p>
          <Link to="/games" className="btn btn-primary" style={{ alignSelf: "flex-start" }}>
            Play another game
          </Link>
        </div>
      </div>
    );
  }

  if (!round) return null;

  return (
    <div className="stack">
      <div className="row-between">
        <h1>
          Round {round.round_number} / {round.total_rounds}
        </h1>
        <Link to="/games" className="muted">
          Exit game
        </Link>
      </div>

      {result && (
        <div className={`alert ${result.correct ? "alert-info" : "alert-danger"}`}>
          {result.correct ? "Correct!" : "Not quite."} Score so far: {result.score}
        </div>
      )}

      <div className="card stack">
        {round.word && (
          <>
            <p className="muted">What does this word mean?</p>
            <h2>{round.word}</h2>
            <div className="stack">
              {round.options.map((opt) => (
                <button key={opt} className="btn btn-outline" onClick={() => answer(opt)} type="button">
                  {opt}
                </button>
              ))}
            </div>
          </>
        )}

        {round.prompt_text && (
          <>
            <p className="muted">Identify the sound/word:</p>
            <h2>{round.prompt_text}</h2>
            <FreeTextAnswer onSubmit={answer} />
          </>
        )}
      </div>
    </div>
  );
}

function FreeTextAnswer({ onSubmit }) {
  const [value, setValue] = useState("");
  return (
    <form
      className="row"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(value);
        setValue("");
      }}
    >
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Type your answer"
        style={{ flex: 1, borderRadius: 8, border: "1.5px solid var(--color-border)", padding: 8 }}
      />
      <button className="btn btn-primary" type="submit">
        Submit
      </button>
    </form>
  );
}
