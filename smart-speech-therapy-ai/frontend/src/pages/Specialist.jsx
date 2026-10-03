import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import WaveDivider from "../components/WaveDivider";

/**
 * Specialist workspace (spec section 25): a single place to review the
 * queue of completed assessments and AI-drafted therapy plans awaiting
 * clinical sign-off. Every number here comes straight from the API —
 * nothing on this page is invented or simulated client-side.
 */
export default function Specialist() {
  const [assessments, setAssessments] = useState([]);
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notes, setNotes] = useState({});
  const [expanded, setExpanded] = useState(null);
  const [resultCache, setResultCache] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [pendingAssessments, pendingPlans] = await Promise.all([
        api.get("/assessments/pending-review"),
        api.get("/therapy-plans/pending-review"),
      ]);
      setAssessments(pendingAssessments);
      setPlans(pendingPlans);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load the review queue");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function toggleExpand(assessmentId) {
    if (expanded === assessmentId) {
      setExpanded(null);
      return;
    }
    setExpanded(assessmentId);
    if (!resultCache[assessmentId]) {
      try {
        const result = await api.get(`/assessments/${assessmentId}/result`);
        setResultCache((c) => ({ ...c, [assessmentId]: result }));
      } catch {
        // Non-fatal: the card still shows the basic summary without detail.
      }
    }
  }

  async function reviewAssessment(assessmentId, approve) {
    setError(null);
    try {
      await api.post(`/assessments/${assessmentId}/review`, {
        approve,
        notes: notes[`a-${assessmentId}`] || null,
      });
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not submit assessment review");
    }
  }

  async function reviewPlan(planId, approve) {
    setError(null);
    try {
      await api.post(`/therapy-plans/${planId}/review`, { approve, notes: notes[`p-${planId}`] || null });
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not submit plan review");
    }
  }

  return (
    <div className="stack">
      <div>
        <h1>Specialist Workspace</h1>
        <p>Assessments and AI-drafted plans waiting for your review. Nothing here is final until you sign off.</p>
      </div>

      {loading && <WaveDivider animated />}
      {error && <div className="alert alert-danger">{error}</div>}

      <section className="stack">
        <div className="row-between">
          <h2 style={{ margin: 0 }}>Assessments ({assessments.length})</h2>
        </div>
        {!loading && assessments.length === 0 && (
          <p className="muted">No completed assessments are waiting for review.</p>
        )}
        {assessments.map((a) => {
          const result = resultCache[a.id];
          const isOpen = expanded === a.id;
          return (
            <div key={a.id} className="card stack">
              <div className="row-between">
                <div>
                  <strong>{a.assessment_type} assessment</strong>
                  <span className="muted"> — {new Date(a.created_at).toLocaleString()}</span>
                </div>
                <span className="badge badge-primary">{a.status}</span>
              </div>

              <button className="btn btn-outline" type="button" onClick={() => toggleExpand(a.id)}>
                {isOpen ? "Hide details" : "View AI findings & evidence"}
              </button>

              {isOpen && (
                <div className="stack" style={{ background: "var(--color-surface-muted)", borderRadius: 8, padding: 12 }}>
                  {!result && <span className="muted">Loading…</span>}
                  {result && (
                    <>
                      {result.summary && <p>{result.summary}</p>}
                      {result.transcription?.text && (
                        <p className="muted">
                          Transcript ({result.transcription.evidence_source}): "{result.transcription.text}"
                        </p>
                      )}
                      {result.pronunciation?.available && (
                        <p className="muted">
                          Pronunciation match: {Math.round(result.pronunciation.accuracy * 100)}% against reference
                          text "{result.pronunciation.reference_text}"
                        </p>
                      )}
                      {result.limitations?.length > 0 && (
                        <ul className="muted">
                          {result.limitations.map((l, i) => (
                            <li key={i}>{l}</li>
                          ))}
                        </ul>
                      )}
                      {result.evidence?.length > 0 && (
                        <div className="stack">
                          <strong>Supporting evidence</strong>
                          {result.evidence.map((e) => (
                            <p key={e.chunk_id} className="muted">
                              {e.title}
                              {e.page_number ? `, p.${e.page_number}` : ""} — {e.content.slice(0, 160)}…
                            </p>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}

              <textarea
                placeholder="Review notes (optional)"
                value={notes[`a-${a.id}`] || ""}
                onChange={(e) => setNotes((n) => ({ ...n, [`a-${a.id}`]: e.target.value }))}
                rows={2}
                style={{ borderRadius: 8, border: "1.5px solid var(--color-border)", padding: 8 }}
              />
              <div className="row">
                <button className="btn btn-primary" type="button" onClick={() => reviewAssessment(a.id, true)}>
                  Approve
                </button>
                <button className="btn btn-danger" type="button" onClick={() => reviewAssessment(a.id, false)}>
                  Flag / Reject
                </button>
              </div>
            </div>
          );
        })}
      </section>

      <section className="stack">
        <h2>Therapy Plans ({plans.length})</h2>
        {!loading && plans.length === 0 && <p className="muted">No draft plans are waiting for review.</p>}
        {plans.map((p) => (
          <div key={p.id} className="card stack">
            <div className="row-between">
              <strong>{p.duration_weeks ? `${p.duration_weeks}-week plan` : "Support plan"}</strong>
              <span className="badge badge-accent">{p.status}</span>
            </div>
            <p className="muted">{p.goals}</p>
            <textarea
              placeholder="Review notes (optional)"
              value={notes[`p-${p.id}`] || ""}
              onChange={(e) => setNotes((n) => ({ ...n, [`p-${p.id}`]: e.target.value }))}
              rows={2}
              style={{ borderRadius: 8, border: "1.5px solid var(--color-border)", padding: 8 }}
            />
            <div className="row">
              <button className="btn btn-primary" type="button" onClick={() => reviewPlan(p.id, true)}>
                Approve
              </button>
              <button className="btn btn-danger" type="button" onClick={() => reviewPlan(p.id, false)}>
                Reject
              </button>
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}
