import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LangContext";
import { api } from "../lib/api";
import WaveDivider from "../components/WaveDivider";

export default function Dashboard() {
  const { user } = useAuth();
  const { t } = useLang();
  const [assessments, setAssessments] = useState([]);
  const [plans, setPlans] = useState([]);
  const [history, setHistory] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const [a, p, h, n] = await Promise.allSettled([
        api.get("/assessments/me"),
        api.get("/therapy-plans/me"),
        api.get("/exercises/me/history"),
        api.get("/notifications?unread_only=true"),
      ]);
      if (cancelled) return;
      setAssessments(a.status === "fulfilled" ? a.value : []);
      setPlans(p.status === "fulfilled" ? p.value : []);
      setHistory(h.status === "fulfilled" ? h.value : []);
      setNotifications(n.status === "fulfilled" ? n.value : []);
      setLoading(false);
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const avgScore = history.length
    ? Math.round(history.reduce((sum, c) => sum + (c.score || 0), 0) / history.length)
    : null;

  return (
    <div className="stack">
      <div>
        <h1>
          {t("dashboard_welcome")}, {user?.full_name?.split(" ")[0] || user?.email}
        </h1>
        <p>{t("dashboard_subtitle")}</p>
      </div>

      <WaveDivider animated={loading} />

      {notifications.length > 0 && (
        <div className="alert alert-info">
          {notifications.length} unread notification{notifications.length > 1 ? "s" : ""} — most recent:{" "}
          <strong>{notifications[0].title}</strong>
        </div>
      )}

      <div className="grid grid-cols-3">
        <StatCard label="Assessments" value={assessments.length} />
        <StatCard label="Exercises completed" value={history.length} />
        <StatCard label="Average exercise score" value={avgScore !== null ? `${avgScore}%` : "—"} />
      </div>

      <div className="grid grid-cols-2">
        <div className="card">
          <div className="section-title-row">
            <h3>Recent assessments</h3>
            <Link to="/assessment">View all</Link>
          </div>
          {assessments.length === 0 && <p className="muted">No assessments yet — start one to get screening feedback.</p>}
          <div className="stack" style={{ gap: 8 }}>
            {assessments.slice(0, 5).map((a) => (
              <div key={a.id} className="row-between">
                <span>{a.assessment_type} assessment</span>
                <StatusBadge status={a.status} />
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="section-title-row">
            <h3>Support plans</h3>
            <Link to="/plans">View all</Link>
          </div>
          {plans.length === 0 && <p className="muted">No support plans yet.</p>}
          <div className="stack" style={{ gap: 8 }}>
            {plans.slice(0, 5).map((p) => (
              <div key={p.id} className="row-between">
                <span>{p.duration_weeks ? `${p.duration_weeks}-week plan` : "Plan"}</span>
                <StatusBadge status={p.status} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value }) {
  return (
    <div className="card">
      <div className="muted">{label}</div>
      <div style={{ fontFamily: "var(--font-display)", fontSize: "var(--text-2xl)", fontWeight: 700 }}>{value}</div>
    </div>
  );
}

function StatusBadge({ status }) {
  const map = {
    completed: "badge-primary",
    approved: "badge-primary",
    ai_draft: "badge-accent",
    pending: "badge",
    processing: "badge-accent",
    failed: "badge-danger",
    rejected: "badge-danger",
  };
  return <span className={`badge ${map[status] || "badge"}`}>{status}</span>;
}
