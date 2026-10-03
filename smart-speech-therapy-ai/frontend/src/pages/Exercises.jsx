import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import WaveDivider from "../components/WaveDivider";

const CATEGORIES = ["all", "fluency", "pronunciation", "articulation", "vocabulary", "language", "voice", "communication"];

export default function Exercises() {
  const [exercises, setExercises] = useState([]);
  const [category, setCategory] = useState("all");
  const [loading, setLoading] = useState(true);
  const [activeExercise, setActiveExercise] = useState(null);
  const [score, setScore] = useState(80);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    setLoading(true);
    const path = category === "all" ? "/exercises" : `/exercises?category=${category}`;
    api
      .get(path)
      .then(setExercises)
      .finally(() => setLoading(false));
  }, [category]);

  async function submitCompletion(exerciseId) {
    setMessage(null);
    try {
      await api.post(`/exercises/${exerciseId}/complete`, { score: Number(score) });
      setMessage({ type: "success", text: "Nice work — completion recorded." });
      setActiveExercise(null);
    } catch (e) {
      setMessage({ type: "error", text: e instanceof ApiError ? e.message : "Could not record completion" });
    }
  }

  return (
    <div className="stack">
      <div>
        <h1>Exercises</h1>
        <p>Practice activities across fluency, pronunciation, voice, and general communication.</p>
      </div>

      <div className="row" style={{ flexWrap: "wrap" }}>
        {CATEGORIES.map((c) => (
          <button
            key={c}
            className={`btn ${category === c ? "btn-primary" : "btn-outline"}`}
            onClick={() => setCategory(c)}
            type="button"
          >
            {c}
          </button>
        ))}
      </div>

      {message && <div className={`alert ${message.type === "success" ? "alert-info" : "alert-danger"}`}>{message.text}</div>}
      {loading && <WaveDivider animated />}

      <div className="grid grid-cols-2">
        {exercises.map((ex) => (
          <div key={ex.id} className="card stack">
            <div className="row-between">
              <h3>{ex.title}</h3>
              <span className="badge badge-primary">{ex.category}</span>
            </div>
            <p>{ex.instructions}</p>
            <div className="row muted">
              {ex.duration_minutes && <span>{ex.duration_minutes} min</span>}
              <span>{ex.difficulty}</span>
            </div>

            {activeExercise === ex.id ? (
              <div className="row">
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={score}
                  onChange={(e) => setScore(e.target.value)}
                  style={{ width: 80, borderRadius: 8, border: "1.5px solid var(--color-border)", padding: 8 }}
                />
                <button className="btn btn-primary" onClick={() => submitCompletion(ex.id)} type="button">
                  Confirm score
                </button>
                <button className="btn btn-outline" onClick={() => setActiveExercise(null)} type="button">
                  Cancel
                </button>
              </div>
            ) : (
              <button className="btn btn-accent" onClick={() => setActiveExercise(ex.id)} type="button">
                Mark as completed
              </button>
            )}
          </div>
        ))}
      </div>

      {!loading && exercises.length === 0 && (
        <div className="card">
          <p className="muted">No exercises in this category yet.</p>
        </div>
      )}
    </div>
  );
}
