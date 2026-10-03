import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import WaveDivider from "../components/WaveDivider";

const MEDIA_TYPES = {
  audio: { label: "Audio", accept: ".wav,.mp3,.m4a,.flac,.ogg", endpoint: "/assessments/media/audio" },
  image: { label: "Image", accept: ".jpg,.jpeg,.png,.webp", endpoint: "/assessments/media/image" },
  video: { label: "Video", accept: ".mp4,.mov,.webm", endpoint: "/assessments/media/video" },
};

export default function Assessment() {
  const [assessments, setAssessments] = useState([]);
  const [mediaType, setMediaType] = useState("audio");
  const [file, setFile] = useState(null);
  const [referenceText, setReferenceText] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [evidence, setEvidence] = useState(null);

  function loadAssessments() {
    api.get("/assessments/me").then(setAssessments);
  }

  useEffect(loadAssessments, []);

  // Poll while the selected assessment is still processing — analysis now
  // runs in a background task (not blocking the request), so the frontend
  // needs to check back for the result instead of getting it immediately.
  useEffect(() => {
    if (!selected || !["pending", "processing"].includes(selected.status)) return;
    const interval = setInterval(async () => {
      const updated = await api.get(`/assessments/${selected.id}`);
      setSelected(updated);
      setAssessments((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
      if (!["pending", "processing"].includes(updated.status)) clearInterval(interval);
    }, 2000);
    return () => clearInterval(interval);
  }, [selected]);

  async function handleUpload(e) {
    e.preventDefault();
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const media = await api.postForm(MEDIA_TYPES[mediaType].endpoint, formData);
      const payload = { media_file_id: media.id, assessment_type: mediaType };
      if (mediaType === "audio" && referenceText.trim()) payload.reference_text = referenceText.trim();
      const assessment = await api.post("/assessments", payload);
      setAssessments((prev) => [assessment, ...prev]);
      setSelected(assessment);
      setEvidence(null);
      setFile(null);
      setReferenceText("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function viewEvidence(assessment) {
    setSelected(assessment);
    setEvidence(null);
    const ev = await api.get(`/assessments/${assessment.id}/evidence`);
    setEvidence(ev.excerpts);
  }

  async function generatePlan(assessmentId) {
    setError(null);
    try {
      await api.post(`/therapy-plans/generate/${assessmentId}`, {});
      alert("A draft support plan was generated — a specialist will review it before it's final. See Therapy Plans.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not generate a support plan");
    }
  }

  const features = selected?.analysis_result ? JSON.parse(selected.analysis_result.features_json) : null;

  return (
    <div className="stack">
      <div>
        <h1>Assessment</h1>
        <p>
          Upload audio, an image, or a short video for an AI-assisted screening. This is not a diagnosis — real
          computed signal/geometric features only, always reviewed against your own judgement and, ideally, a
          specialist.
        </p>
      </div>

      <form className="card stack" onSubmit={handleUpload}>
        <div className="row">
          {Object.entries(MEDIA_TYPES).map(([key, cfg]) => (
            <button
              key={key}
              type="button"
              className={`btn ${mediaType === key ? "btn-primary" : "btn-outline"}`}
              onClick={() => {
                setMediaType(key);
                setFile(null);
              }}
            >
              {cfg.label}
            </button>
          ))}
        </div>
        <div className="row">
          <input
            type="file"
            accept={MEDIA_TYPES[mediaType].accept}
            onChange={(e) => setFile(e.target.files[0])}
            key={mediaType}
          />
          <button className="btn btn-primary" type="submit" disabled={!file || uploading}>
            {uploading ? "Processing…" : "Upload & analyze"}
          </button>
        </div>
        {mediaType === "audio" && (
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="reference-text">
              What word or phrase were you asked to say? (optional — enables pronunciation comparison)
            </label>
            <input
              id="reference-text"
              type="text"
              placeholder='e.g. "the quick brown fox"'
              value={referenceText}
              onChange={(e) => setReferenceText(e.target.value)}
            />
          </div>
        )}
      </form>
      {uploading && <WaveDivider animated />}
      {error && <div className="alert alert-danger">{error}</div>}

      <div className="grid grid-cols-2">
        <div className="stack">
          <h3>Your assessments</h3>
          {assessments.map((a) => (
            <button
              key={a.id}
              className="card"
              style={{ textAlign: "start", cursor: "pointer" }}
              onClick={() => viewEvidence(a)}
              type="button"
            >
              <div className="row-between">
                <span>{a.assessment_type} assessment</span>
                <span className="badge badge-primary">{a.status}</span>
              </div>
            </button>
          ))}
          {assessments.length === 0 && <p className="muted">No assessments yet.</p>}
        </div>

        <div className="stack">
          {selected && (
            <div className="card stack">
              <h3>Result</h3>
              {selected.analysis_result ? (
                <>
                  <p>{selected.analysis_result.summary}</p>
                  <div className="muted">
                    Model: {selected.analysis_result.model_name} · Input quality:{" "}
                    {Math.round((selected.analysis_result.input_quality_score || 0) * 100)}%
                  </div>

                  {selected.assessment_type === "audio" && features && (
                    <AudioFeaturesPanel features={features} />
                  )}
                  {selected.assessment_type === "image" && features && (
                    <ImageFeaturesPanel features={features} />
                  )}
                  {selected.assessment_type === "video" && features && (
                    <VideoFeaturesPanel features={features} />
                  )}

                  <details>
                    <summary>Limitations</summary>
                    <p className="muted" style={{ whiteSpace: "pre-line" }}>
                      {selected.analysis_result.limitations}
                    </p>
                  </details>
                  <button className="btn btn-accent" onClick={() => generatePlan(selected.id)} type="button">
                    Generate draft support plan
                  </button>
                </>
              ) : (
                <p className="muted row">
                  <WaveDivider animated height={16} /> Still processing…
                </p>
              )}

              {evidence && (
                <div className="stack">
                  <h3>Why this result? Related evidence</h3>
                  {evidence.length === 0 && <p className="muted">No specific Knowledge Base evidence retrieved.</p>}
                  {evidence.map((ex) => (
                    <div key={ex.chunk_id} className="card" style={{ background: "var(--color-surface-muted)" }}>
                      <p style={{ marginBottom: 4 }}>{ex.content.slice(0, 240)}…</p>
                      <div className="muted" style={{ fontSize: "var(--text-xs)" }}>
                        {ex.title} {ex.author ? `— ${ex.author}` : ""} {ex.publication_year || ""}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function AudioFeaturesPanel({ features }) {
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="mono muted" style={{ fontSize: "var(--text-xs)" }}>
        duration {features.duration_seconds}s · pitch {features.pitch_mean_hz ? `${features.pitch_mean_hz} Hz` : "n/a"} ·
        pauses {features.pause_count} · speaking ratio {(features.speaking_rate_estimate * 100).toFixed(0)}%
      </div>
      {features.stuttering_classification?.available ? (
        <div className="alert alert-info">
          <span className="badge badge-primary" style={{ marginInlineEnd: 6 }}>
            Trained model
          </span>
          <strong>Stuttering-event classification:</strong> most likely —{" "}
          <strong>{features.stuttering_classification.predicted_label}</strong>
          <div className="muted" style={{ marginTop: 4, fontSize: "var(--text-xs)" }}>
            {Object.entries(features.stuttering_classification.label_scores)
              .sort((a, b) => b[1] - a[1])
              .map(([label, score]) => `${label}: ${(score * 100).toFixed(0)}%`)
              .join(" · ")}
          </div>
          <div className="muted" style={{ marginTop: 4 }}>
            {features.stuttering_classification.note}
          </div>
        </div>
      ) : (
        features.fluency_indicators && (
          <div className="alert alert-info">
            <strong>Fluency screening (heuristic, unvalidated):</strong>{" "}
            {features.fluency_indicators.repetition_candidate_count} repetition-like,{" "}
            {features.fluency_indicators.prolongation_candidate_count} prolongation-like,{" "}
            {features.fluency_indicators.abrupt_cutoff_count} abrupt-cutoff pattern(s).
            <div className="muted" style={{ marginTop: 4 }}>
              Signal-processing heuristics, not a trained clinical classifier — candidate patterns for specialist
              review only. A real trained classifier is used automatically when the server has HF_API_TOKEN
              configured.
            </div>
          </div>
        )
      )}
      {features.transcript && (
        <div className="alert alert-info">
          <strong>Rough transcript (low-confidence, offline ASR):</strong> "{features.transcript}"
          <div className="muted" style={{ marginTop: 4 }}>
            Generated with {features.transcript_model}. Treat as an approximation, not a reliable source of truth.
          </div>
        </div>
      )}
      {features.pronunciation?.available && <PronunciationPanel pronunciation={features.pronunciation} />}
    </div>
  );
}

function PronunciationPanel({ pronunciation }) {
  return (
    <div className="alert alert-info">
      <strong>Pronunciation comparison:</strong> {Math.round(pronunciation.accuracy * 100)}% word-level match against
      "{pronunciation.reference_text}"
      <div className="row" style={{ flexWrap: "wrap", gap: 6, marginTop: 8 }}>
        {pronunciation.word_comparisons.map((w, i) => (
          <span
            key={i}
            className="badge"
            title={`${w.mismatch_type} · confidence ${Math.round(w.confidence * 100)}%`}
            style={{
              background: w.match ? "var(--color-primary-soft)" : "var(--color-danger-soft)",
              color: w.match ? "var(--color-primary-dark)" : "var(--color-danger)",
            }}
          >
            {w.expected || `[+${w.recognized}]`}
            {!w.match && w.recognized ? ` → ${w.recognized}` : ""}
          </span>
        ))}
      </div>
      <div className="muted" style={{ marginTop: 8, fontSize: "var(--text-xs)" }}>
        {pronunciation.note} Word-level confidence reflects the reliability of the speech recognizer used, not a
        clinical pronunciation score.
      </div>
    </div>
  );
}

function ImageFeaturesPanel({ features }) {
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="mono muted" style={{ fontSize: "var(--text-xs)" }}>
        face detected: {features.face_detected ? "yes" : "no"} · eyes detected: {features.eyes_detected} ·
        {features.symmetry_score != null && <> symmetry score: {features.symmetry_score.toFixed(2)} ·</>}
        resolution: {features.resolution?.[0]}×{features.resolution?.[1]}
      </div>
      {features.description && (
        <div className="alert alert-info">
          <strong>AI description (observational only):</strong> {features.description}
        </div>
      )}
    </div>
  );
}

function VideoFeaturesPanel({ features }) {
  const vs = features.video_summary;
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="mono muted" style={{ fontSize: "var(--text-xs)" }}>
        duration {vs.duration_seconds}s · frames sampled {vs.frames_sampled} · faces detected in{" "}
        {vs.faces_detected_in_frames} of {vs.frames_sampled} frame(s) · audio extracted: {vs.audio_extracted ? "yes" : "no"}
      </div>
      {features.audio_result && (
        <div className="mono muted" style={{ fontSize: "var(--text-xs)" }}>
          pitch: {features.audio_result.features.pitch_mean_hz ? `${features.audio_result.features.pitch_mean_hz} Hz` : "n/a"}
        </div>
      )}
      {features.fluency_result && (
        <div className="alert alert-info">
          <strong>Fluency screening (heuristic, unvalidated):</strong>{" "}
          {features.fluency_result.repetition_candidate_count} repetition-like,{" "}
          {features.fluency_result.prolongation_candidate_count} prolongation-like pattern(s).
        </div>
      )}
    </div>
  );
}
