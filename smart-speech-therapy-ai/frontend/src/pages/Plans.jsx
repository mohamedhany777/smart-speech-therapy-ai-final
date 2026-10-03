import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { api, ApiError } from "../lib/api";
import WaveDivider from "../components/WaveDivider";

export default function Plans() {
  const { hasRole } = useAuth();
  // Approval is SPECIALIST-only (spec section 16 / backend enforcement —
  // see docs/FINAL_UPGRADE_PLAN.md Stage 2): an ADMIN can see the queue for
  // oversight, but the review buttons must not be shown to a role that the
  // API will now reject with 403. Showing a button that always fails isn't
  // a minor cosmetic bug — it actively misleads an admin into thinking
  // they can approve a patient's plan when they can't.
  const canApprove = hasRole("SPECIALIST");
  const canViewQueue = hasRole("SPECIALIST") || hasRole("ADMIN");
  const [myPlans, setMyPlans] = useState([]);
  const [pending, setPending] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notes, setNotes] = useState({});

  async function load() {
    setLoading(true);
    try {
      const [mine, pend] = await Promise.all([
        api.get("/therapy-plans/me"),
        canViewQueue ? api.get("/therapy-plans/pending-review") : Promise.resolve([]),
      ]);
      setMyPlans(mine);
      setPending(pend);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load plans");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canViewQueue]);

  async function review(planId, approve) {
    setError(null);
    try {
      await api.post(`/therapy-plans/${planId}/review`, { approve, notes: notes[planId] || null });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit review");
    }
  }

  return (
    <div className="stack">
      <div>
        <h1>Therapy Plans</h1>
        <p>AI-drafted support plans always require specialist review before they're considered final.</p>
      </div>

      {loading && <WaveDivider animated />}
      {error && <div className="alert alert-danger">{error}</div>}

      <div className="stack">
        <h3>My plans</h3>
        {myPlans.length === 0 && <p className="muted">No plans yet — generate one from a completed assessment.</p>}
        {myPlans.map((p) => (
          <PlanCard key={p.id} plan={p} />
        ))}
      </div>

      {canViewQueue && (
        <div className="stack">
          <h3>Pending review{!canApprove ? " (oversight)" : ""}</h3>
          {!canApprove && (
            <p className="muted">
              You can see the queue, but only a specialist can approve or reject a plan.
            </p>
          )}
          {pending.length === 0 && <p className="muted">Nothing pending.</p>}
          {pending.map((p) => (
            <div key={p.id} className="card stack">
              <PlanCard plan={p} />
              {canApprove && (
                <>
                  <textarea
                    placeholder="Review notes (optional)"
                    value={notes[p.id] || ""}
                    onChange={(e) => setNotes((n) => ({ ...n, [p.id]: e.target.value }))}
                    rows={2}
                    style={{ borderRadius: 8, border: "1.5px solid var(--color-border)", padding: 8 }}
                  />
                  <div className="row">
                    <button className="btn btn-primary" onClick={() => review(p.id, true)} type="button">
                      Approve
                    </button>
                    <button className="btn btn-danger" onClick={() => review(p.id, false)} type="button">
                      Reject
                    </button>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function PlanCard({ plan }) {
  return (
    <div className="card stack">
      <div className="row-between">
        <h3>{plan.duration_weeks ? `${plan.duration_weeks}-week plan` : "Support plan"}</h3>
        <span className="badge badge-accent">{plan.status}</span>
      </div>
      <p>{plan.goals}</p>
      {plan.items?.length > 0 && (
        <ul className="muted">
          {plan.items.map((item) => (
            <li key={item.id}>
              {item.item_type} — {item.frequency} {item.notes ? `(${item.notes})` : ""}
            </li>
          ))}
        </ul>
      )}
      {plan.reviewer_notes && <p className="muted">Specialist notes: {plan.reviewer_notes}</p>}
    </div>
  );
}
