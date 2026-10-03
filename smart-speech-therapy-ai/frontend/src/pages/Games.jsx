import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import WaveDivider from "../components/WaveDivider";

export default function Games() {
  const [games, setGames] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    api
      .get("/games")
      .then(setGames)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  async function startGame(gameId) {
    setError(null);
    try {
      const session = await api.post(`/games/${gameId}/start`, {});
      navigate(`/games/${session.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start game");
    }
  }

  return (
    <div className="stack">
      <div>
        <h1>Games</h1>
        <p>Playful practice — every round is scored for real, no placeholder results.</p>
      </div>

      {loading && <WaveDivider animated />}
      {error && <div className="alert alert-danger">{error}</div>}

      <div className="grid grid-cols-2">
        {games.map((g) => (
          <div key={g.id} className="card stack">
            <div className="row-between">
              <h3>{g.title}</h3>
              <span className="badge badge-accent">{g.difficulty}</span>
            </div>
            <p>{g.description}</p>
            <button className="btn btn-primary" onClick={() => startGame(g.id)} type="button">
              Play
            </button>
          </div>
        ))}
      </div>

      {!loading && games.length === 0 && (
        <div className="card">
          <p className="muted">No games available yet.</p>
        </div>
      )}
    </div>
  );
}
