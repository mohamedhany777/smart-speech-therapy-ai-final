import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import WaveDivider from "../components/WaveDivider";

export default function Disorders() {
  const [disorders, setDisorders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    api
      .get("/disorders")
      .then(setDisorders)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="stack">
      <div>
        <h1>Disorders</h1>
        <p>
          A database-driven reference of communication, speech, language, and voice disorders. This is
          educational information, not a diagnostic tool.
        </p>
      </div>

      {loading && <WaveDivider animated />}
      {error && <div className="alert alert-danger">{error}</div>}

      <div className="grid grid-cols-2">
        {disorders.map((d) => (
          <Link key={d.id} to={`/disorders/${d.slug}`} className="card" style={{ textDecoration: "none", color: "inherit" }}>
            <h3>{d.name}</h3>
            <p className="muted">{(d.overview || "").slice(0, 140)}{d.overview && d.overview.length > 140 ? "…" : ""}</p>
          </Link>
        ))}
      </div>

      {!loading && disorders.length === 0 && (
        <div className="card">
          <p className="muted">No disorders have been added yet. An admin can add the taxonomy from the Admin panel.</p>
        </div>
      )}
    </div>
  );
}
