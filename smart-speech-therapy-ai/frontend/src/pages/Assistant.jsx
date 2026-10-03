import { useState } from "react";
import { api, ApiError } from "../lib/api";
import WaveDivider from "../components/WaveDivider";

export default function Assistant() {
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setAnswer(null);
    try {
      const result = await api.post("/knowledge-base/query", { query });
      setAnswer(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Query failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="stack">
      <div>
        <h1>AI Assistant</h1>
        <p>Ask questions about disorders, exercises, or research. Every answer is traceable to a real source.</p>
      </div>

      <form className="card row" onSubmit={handleSubmit}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. What is stuttering and how is it assessed?"
          style={{ flex: 1, borderRadius: 8, border: "1.5px solid var(--color-border)", padding: 8 }}
        />
        <button className="btn btn-primary" type="submit" disabled={loading}>
          Ask
        </button>
      </form>

      {loading && <WaveDivider animated />}
      {error && <div className="alert alert-danger">{error}</div>}

      {answer && (
        <div className="stack">
          <div className={`alert ${answer.source_status === "no_source_found" ? "alert-danger" : "alert-info"}`}>
            <strong>Source status:</strong> {answer.source_status.replaceAll("_", " ")}
            <br />
            {answer.message}
          </div>

          {answer.generated_answer && (
            <div className="card" style={{ borderColor: "var(--color-primary)" }}>
              <div className="badge badge-primary" style={{ marginBottom: 8 }}>
                AI-generated answer
              </div>
              <p>{answer.generated_answer}</p>
              <p className="muted">Grounded strictly in the excerpts below — verify against the original sources.</p>
            </div>
          )}

          {answer.source_status === "based_on_web_sources" && (
            <div className="alert alert-info">
              These are live web search results, ranked by source trust (government/academic/professional
              organizations ranked highest) — not Knowledge Base documents.
            </div>
          )}

          {answer.excerpts.map((ex) => (
            <div key={ex.chunk_id || ex.source_url} className="card">
              <p>{ex.content}</p>
              <div className="row-between muted" style={{ fontSize: "var(--text-sm)" }}>
                <span>
                  {ex.source_type === "web" ? (
                    <a href={ex.source_url} target="_blank" rel="noreferrer">
                      {ex.title || ex.source_url}
                    </a>
                  ) : (
                    <>
                      {ex.title}
                      {ex.author ? ` — ${ex.author}` : ""}
                      {ex.publication_year ? ` (${ex.publication_year})` : ""}
                      {ex.page_number ? `, p.${ex.page_number}` : ""}
                    </>
                  )}
                </span>
                <span className="badge">{Math.round(ex.relevance_score * 100)}% match</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
