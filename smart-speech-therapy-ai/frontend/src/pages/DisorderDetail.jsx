import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../lib/api";
import WaveDivider from "../components/WaveDivider";

export default function DisorderDetail() {
  const { slug } = useParams();
  const [disorder, setDisorder] = useState(null);
  const [exercises, setExercises] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    api
      .get(`/disorders/${slug}`)
      .then(async (d) => {
        setDisorder(d);
        const all = await api.get("/exercises");
        setExercises(all.filter((e) => e.disorder_id === d.id));
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [slug]);

  if (loading) return <WaveDivider animated />;
  if (error) return <div className="alert alert-danger">{error}</div>;
  if (!disorder) return null;

  return (
    <div className="stack">
      <Link to="/disorders">← Back to disorders</Link>
      <h1>{disorder.name}</h1>

      <Section title="Overview" text={disorder.overview} />
      <Section title="Possible characteristics" text={disorder.possible_characteristics} />
      <Section title="Speech features" text={disorder.speech_features} />
      <Section title="Assessment notes" text={disorder.assessment_notes} />

      <div className="card">
        <h3>Related exercises</h3>
        {exercises.length === 0 && <p className="muted">No linked exercises yet.</p>}
        <div className="stack" style={{ gap: 8 }}>
          {exercises.map((ex) => (
            <div key={ex.id} className="row-between">
              <span>{ex.title}</span>
              <span className="badge">{ex.category}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="alert alert-info">
        AI screening in this platform is based on acoustic pattern detection only and is not a diagnosis.
        A professional assessment is recommended for any concerns.
      </div>
    </div>
  );
}

function Section({ title, text }) {
  if (!text) return null;
  return (
    <div className="card">
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}
