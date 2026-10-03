import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { api, ApiError } from "../lib/api";
import WaveDivider from "../components/WaveDivider";

const TABS = ["Overview", "Users", "Disorders", "Exercises", "Knowledge Base", "AI Models", "Audit Log"];

export default function Admin() {
  const { hasRole } = useAuth();
  const [tab, setTab] = useState("Overview");

  if (!hasRole("ADMIN")) {
    return <div className="alert alert-danger">Admin access required.</div>;
  }

  return (
    <div className="stack">
      <h1>Admin</h1>
      <div className="row">
        {TABS.map((t) => (
          <button key={t} className={`btn ${tab === t ? "btn-primary" : "btn-outline"}`} onClick={() => setTab(t)} type="button">
            {t}
          </button>
        ))}
      </div>

      {tab === "Overview" && <Overview />}
      {tab === "Users" && <Users />}
      {tab === "Disorders" && <DisordersAdmin />}
      {tab === "Exercises" && <ExercisesAdmin />}
      {tab === "Knowledge Base" && <KnowledgeBaseAdmin />}
      {tab === "AI Models" && <ModelRegistryAdmin />}
      {tab === "Audit Log" && <AuditLog />}
    </div>
  );
}

function Overview() {
  const [stats, setStats] = useState(null);
  useEffect(() => {
    api.get("/admin/analytics").then(setStats);
  }, []);
  if (!stats) return <WaveDivider animated />;
  return (
    <div className="grid grid-cols-3">
      {Object.entries(stats).map(([key, value]) => (
        <div key={key} className="card">
          <div className="muted">{key.replaceAll("_", " ")}</div>
          <div style={{ fontFamily: "var(--font-display)", fontSize: "var(--text-2xl)", fontWeight: 700 }}>{value}</div>
        </div>
      ))}
    </div>
  );
}

function Users() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);

  function load() {
    setLoading(true);
    api.get("/admin/users").then(setUsers).finally(() => setLoading(false));
  }
  useEffect(load, []);

  async function deactivate(userId) {
    await api.post(`/admin/users/${userId}/deactivate`, {});
    load();
  }

  if (loading) return <WaveDivider animated />;

  return (
    <div className="card">
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "start" }}>
            <th>Email</th>
            <th>Name</th>
            <th>Roles</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} style={{ borderTop: "1px solid var(--color-border)" }}>
              <td>{u.email}</td>
              <td>{u.full_name}</td>
              <td>{u.roles.join(", ")}</td>
              <td>
                <span className={`badge ${u.is_active ? "badge-primary" : "badge-danger"}`}>
                  {u.is_active ? "active" : "deactivated"}
                </span>
              </td>
              <td>
                {u.is_active && (
                  <button className="btn btn-outline" onClick={() => deactivate(u.id)} type="button">
                    Deactivate
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const DISORDER_FORM_FIELDS = [
  { key: "name", label: "Name", type: "text", required: true },
  { key: "slug", label: "Slug (URL-friendly, unique)", type: "text", required: true },
  { key: "language", label: "Language", type: "select", options: ["en", "ar"] },
  { key: "overview", label: "Overview", type: "textarea" },
  { key: "possible_characteristics", label: "Possible characteristics", type: "textarea" },
  { key: "speech_features", label: "Speech features", type: "textarea" },
  { key: "assessment_notes", label: "Assessment notes", type: "textarea" },
];

const EMPTY_DISORDER = { name: "", slug: "", language: "en", overview: "", possible_characteristics: "", speech_features: "", assessment_notes: "" };

function DisordersAdmin() {
  const [disorders, setDisorders] = useState([]);
  const [editing, setEditing] = useState(null); // null = not editing; {} = new; {...} = existing
  const [form, setForm] = useState(EMPTY_DISORDER);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  // AI extraction state
  const [extractFile, setExtractFile] = useState(null);
  const [extracting, setExtracting] = useState(false);
  const [draft, setDraft] = useState(null);

  function load() {
    api.get("/disorders?include_inactive=true").then(setDisorders);
  }
  useEffect(load, []);

  function startCreate() {
    setEditing({});
    setForm(EMPTY_DISORDER);
    setDraft(null);
    setError(null);
  }

  function startEdit(disorder) {
    setEditing(disorder);
    setForm({ ...EMPTY_DISORDER, ...disorder });
    setDraft(null);
    setError(null);
  }

  function cancelEdit() {
    setEditing(null);
    setDraft(null);
  }

  async function handleExtract(e) {
    e.preventDefault();
    if (!extractFile) return;
    setExtracting(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", extractFile);
      const result = await api.postForm("/disorders/extract-from-document", formData);
      setDraft(result);
      if (result.available) {
        setForm((f) => ({
          ...f,
          name: result.suggested_name || f.name,
          slug: result.suggested_slug || f.slug,
          overview: result.overview || f.overview,
          possible_characteristics: result.possible_characteristics || f.possible_characteristics,
          speech_features: result.speech_features || f.speech_features,
          assessment_notes: result.assessment_notes || f.assessment_notes,
        }));
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Extraction failed");
    } finally {
      setExtracting(false);
    }
  }

  async function handleSave(e) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      if (editing?.id) {
        await api.patch(`/disorders/${editing.id}`, form);
      } else {
        await api.post("/disorders", form);
      }
      setEditing(null);
      setDraft(null);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(disorder) {
    await api.patch(`/disorders/${disorder.id}`, { is_active: !disorder.is_active });
    load();
  }

  if (editing !== null) {
    return (
      <div className="stack">
        <div className="row-between">
          <h3>{editing.id ? `Edit: ${editing.name}` : "New disorder"}</h3>
          <button className="btn btn-outline" onClick={cancelEdit} type="button">
            Cancel
          </button>
        </div>

        {!editing.id && (
          <form className="card stack" onSubmit={handleExtract}>
            <h3>Optional: AI-assisted draft from a document</h3>
            <p className="muted">
              Upload a reference PDF/DOCX/TXT and let AI draft the fields below for you to review and edit —
              nothing is saved automatically. Requires the server's OPENAI_API_KEY to be configured.
            </p>
            <div className="row">
              <input type="file" accept=".pdf,.docx,.txt,.md" onChange={(e) => setExtractFile(e.target.files[0])} />
              <button className="btn btn-accent" type="submit" disabled={!extractFile || extracting}>
                {extracting ? "Analyzing…" : "Extract draft"}
              </button>
            </div>
            {extracting && <WaveDivider animated />}
            {draft && !draft.available && <div className="alert alert-danger">{draft.note}</div>}
            {draft && draft.available && <div className="alert alert-info">{draft.note} Fields below were pre-filled — review before saving.</div>}
          </form>
        )}

        {error && <div className="alert alert-danger">{error}</div>}

        <form className="card stack" onSubmit={handleSave}>
          {DISORDER_FORM_FIELDS.map((f) => (
            <div key={f.key} className="field">
              <label>{f.label}</label>
              {f.type === "textarea" ? (
                <textarea
                  rows={3}
                  value={form[f.key] || ""}
                  onChange={(e) => setForm((prev) => ({ ...prev, [f.key]: e.target.value }))}
                />
              ) : f.type === "select" ? (
                <select value={form[f.key] || ""} onChange={(e) => setForm((prev) => ({ ...prev, [f.key]: e.target.value }))}>
                  {f.options.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  required={f.required}
                  value={form[f.key] || ""}
                  onChange={(e) => setForm((prev) => ({ ...prev, [f.key]: e.target.value }))}
                />
              )}
            </div>
          ))}
          <button className="btn btn-primary" type="submit" disabled={saving} style={{ alignSelf: "flex-start" }}>
            {saving ? "Saving…" : "Save disorder"}
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="row-between">
        <h3>Disorders</h3>
        <button className="btn btn-primary" onClick={startCreate} type="button">
          + New disorder
        </button>
      </div>
      <div className="card">
        {disorders.map((d) => (
          <div key={d.id} className="row-between" style={{ padding: "8px 0", borderTop: "1px solid var(--color-border)" }}>
            <div>
              <span>{d.name}</span>{" "}
              {!d.is_active && <span className="badge badge-danger">inactive</span>}
            </div>
            <div className="row">
              <button className="btn btn-outline" onClick={() => startEdit(d)} type="button">
                Edit
              </button>
              <button className="btn btn-outline" onClick={() => toggleActive(d)} type="button">
                {d.is_active ? "Deactivate" : "Activate"}
              </button>
            </div>
          </div>
        ))}
        {disorders.length === 0 && <p className="muted">No disorders yet.</p>}
      </div>
    </div>
  );
}

const EXERCISE_FORM_FIELDS = [
  { key: "title", label: "Title", type: "text", required: true },
  { key: "category", label: "Category", type: "text", required: true },
  { key: "difficulty", label: "Difficulty", type: "select", options: ["beginner", "intermediate", "advanced"] },
  { key: "language", label: "Language", type: "select", options: ["en", "ar"] },
  { key: "instructions", label: "Instructions", type: "textarea", required: true },
  { key: "goal", label: "Goal", type: "textarea" },
  { key: "duration_minutes", label: "Duration (minutes)", type: "number" },
];

const EMPTY_EXERCISE = { title: "", category: "", difficulty: "beginner", language: "en", instructions: "", goal: "", duration_minutes: "" };

function ExercisesAdmin() {
  const [exercises, setExercises] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_EXERCISE);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  function load() {
    api.get("/exercises?include_inactive=true").then(setExercises);
  }
  useEffect(load, []);

  function startCreate() {
    setEditing({});
    setForm(EMPTY_EXERCISE);
    setError(null);
  }

  function startEdit(exercise) {
    setEditing(exercise);
    setForm({ ...EMPTY_EXERCISE, ...exercise, duration_minutes: exercise.duration_minutes ?? "" });
    setError(null);
  }

  async function handleSave(e) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const payload = { ...form, duration_minutes: form.duration_minutes ? Number(form.duration_minutes) : null };
      if (editing?.id) {
        await api.patch(`/exercises/${editing.id}`, payload);
      } else {
        await api.post("/exercises", payload);
      }
      setEditing(null);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(exercise) {
    await api.patch(`/exercises/${exercise.id}`, { is_active: !exercise.is_active });
    load();
  }

  if (editing !== null) {
    return (
      <div className="stack">
        <div className="row-between">
          <h3>{editing.id ? `Edit: ${editing.title}` : "New exercise"}</h3>
          <button className="btn btn-outline" onClick={() => setEditing(null)} type="button">
            Cancel
          </button>
        </div>
        {error && <div className="alert alert-danger">{error}</div>}
        <form className="card stack" onSubmit={handleSave}>
          {EXERCISE_FORM_FIELDS.map((f) => (
            <div key={f.key} className="field">
              <label>{f.label}</label>
              {f.type === "textarea" ? (
                <textarea
                  rows={3}
                  value={form[f.key] || ""}
                  onChange={(e) => setForm((prev) => ({ ...prev, [f.key]: e.target.value }))}
                />
              ) : f.type === "select" ? (
                <select value={form[f.key] || ""} onChange={(e) => setForm((prev) => ({ ...prev, [f.key]: e.target.value }))}>
                  {f.options.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type={f.type === "number" ? "number" : "text"}
                  required={f.required}
                  value={form[f.key] || ""}
                  onChange={(e) => setForm((prev) => ({ ...prev, [f.key]: e.target.value }))}
                />
              )}
            </div>
          ))}
          <button className="btn btn-primary" type="submit" disabled={saving} style={{ alignSelf: "flex-start" }}>
            {saving ? "Saving…" : "Save exercise"}
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="row-between">
        <h3>Exercises</h3>
        <button className="btn btn-primary" onClick={startCreate} type="button">
          + New exercise
        </button>
      </div>
      <div className="card">
        {exercises.map((ex) => (
          <div key={ex.id} className="row-between" style={{ padding: "8px 0", borderTop: "1px solid var(--color-border)" }}>
            <div>
              <span>{ex.title}</span> <span className="badge">{ex.category}</span>{" "}
              {!ex.is_active && <span className="badge badge-danger">inactive</span>}
            </div>
            <div className="row">
              <button className="btn btn-outline" onClick={() => startEdit(ex)} type="button">
                Edit
              </button>
              <button className="btn btn-outline" onClick={() => toggleActive(ex)} type="button">
                {ex.is_active ? "Deactivate" : "Activate"}
              </button>
            </div>
          </div>
        ))}
        {exercises.length === 0 && <p className="muted">No exercises yet.</p>}
      </div>
    </div>
  );
}

function KnowledgeBaseAdmin() {
  const [documents, setDocuments] = useState([]);
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);

  function load() {
    // include_inactive=true so the admin can see FAILED/unpublished
    // documents too, not just what's currently live in the assistant.
    api.get("/knowledge-base/documents?include_inactive=true").then(setDocuments);
  }
  useEffect(load, []);

  async function upload(e) {
    e.preventDefault();
    if (!file || !title) return;
    setUploading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("title", title);
      if (author) formData.append("author", author);
      await api.postForm("/knowledge-base/documents", formData);
      setFile(null);
      setTitle("");
      setAuthor("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function remove(id) {
    await api.delete(`/knowledge-base/documents/${id}`);
    load();
  }

  async function togglePublish(doc) {
    await api.patch(`/knowledge-base/documents/${doc.id}`, { is_active: !doc.is_active });
    load();
  }

  const STATUS_BADGE = {
    INDEXED: "badge-primary",
    PROCESSING: "badge-accent",
    UPLOADED: "badge-accent",
    FAILED: "badge-danger",
  };

  return (
    <div className="stack">
      <form className="card stack" onSubmit={upload}>
        <h3>Upload document (PDF / DOCX / TXT / MD)</h3>
        <div className="field">
          <label>Title</label>
          <input value={title} onChange={(e) => setTitle(e.target.value)} required />
        </div>
        <div className="field">
          <label>Author</label>
          <input value={author} onChange={(e) => setAuthor(e.target.value)} />
        </div>
        <input type="file" accept=".pdf,.docx,.txt,.md" onChange={(e) => setFile(e.target.files[0])} />
        {error && <div className="alert alert-danger">{error}</div>}
        <button className="btn btn-primary" type="submit" disabled={uploading} style={{ alignSelf: "flex-start" }}>
          {uploading ? "Ingesting…" : "Upload & ingest"}
        </button>
      </form>

      <div className="card">
        <h3>Documents</h3>
        {documents.map((d) => (
          <div key={d.id} className="stack" style={{ padding: "10px 0", borderTop: "1px solid var(--color-border)", gap: 4 }}>
            <div className="row-between">
              <span>
                {d.title} {d.author ? `— ${d.author}` : ""}
              </span>
              <span className={`badge ${STATUS_BADGE[d.status] || "badge-primary"}`}>{d.status}</span>
            </div>
            <div className="row-between">
              <span className="muted" style={{ fontSize: "var(--text-xs)" }}>
                {d.chunk_count} chunk{d.chunk_count === 1 ? "" : "s"} indexed
                {!d.is_active && d.status !== "FAILED" ? " · unpublished (hidden from the assistant)" : ""}
                {d.status === "FAILED" && d.failure_reason ? ` · ${d.failure_reason}` : ""}
              </span>
              <div className="row" style={{ gap: 6 }}>
                {d.status === "INDEXED" && (
                  <button className="btn btn-outline" onClick={() => togglePublish(d)} type="button">
                    {d.is_active ? "Unpublish" : "Publish"}
                  </button>
                )}
                <button className="btn btn-outline" onClick={() => remove(d.id)} type="button">
                  Delete
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ModelRegistryAdmin() {
  const [models, setModels] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api
      .get("/admin/models")
      .then(setModels)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Failed to load model registry"));
  }, []);

  if (error) return <div className="alert alert-danger">{error}</div>;
  if (!models) return <WaveDivider animated />;

  return (
    <div className="stack">
      <p className="muted">
        Every AI model this platform can call, with honestly-verified metadata — see
        docs/FINAL_UPGRADE_PLAN.md for how each entry was checked. Models are swapped via environment variables,
        not here, since changing the active model is a deployment decision.
      </p>
      {models.map((m) => (
        <div key={m.model_name} className="card stack" style={{ gap: 6 }}>
          <div className="row-between">
            <strong>{m.model_name}</strong>
            <div className="row" style={{ gap: 6 }}>
              {m.is_current_default && <span className="badge badge-primary">default</span>}
              <span className={`badge ${m.enabled ? "badge-primary" : "badge-danger"}`}>
                {m.enabled ? "enabled" : "disabled (no credentials configured)"}
              </span>
            </div>
          </div>
          <div className="muted" style={{ fontSize: "var(--text-xs)" }}>
            {m.role.replaceAll("_", " ")} · {m.task} · {m.language} · {m.provider} · {m.license} ·{" "}
            {m.version_or_revision}
          </div>
          <div style={{ fontSize: "var(--text-sm)" }}>{m.validated_note}</div>
          {m.limitations.length > 0 && (
            <ul className="muted" style={{ fontSize: "var(--text-xs)", margin: 0, paddingInlineStart: 18 }}>
              {m.limitations.map((l, i) => (
                <li key={i}>{l}</li>
              ))}
            </ul>
          )}
          {m.configurable_via && (
            <div className="muted" style={{ fontSize: "var(--text-xs)" }}>
              Configurable via <code>{m.configurable_via}</code>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function AuditLog() {
  const [logs, setLogs] = useState([]);
  useEffect(() => {
    api.get("/admin/audit-logs").then(setLogs);
  }, []);
  return (
    <div className="card">
      {logs.map((log) => (
        <div key={log.id} className="row-between mono" style={{ fontSize: "var(--text-sm)", padding: "6px 0", borderTop: "1px solid var(--color-border)" }}>
          <span>{log.action}</span>
          <span className="muted">{new Date(log.created_at).toLocaleString()}</span>
        </div>
      ))}
      {logs.length === 0 && <p className="muted">No audit events yet.</p>}
    </div>
  );
}
