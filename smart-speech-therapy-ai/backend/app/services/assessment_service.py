"""
Assessment engine (spec sections 32-33, 93, 95-96).

Ties together: uploaded media -> real feature extraction -> input quality
check -> structured AnalysisResult -> relevant Knowledge Base evidence.
Always uses screening language ("patterns associated with...", "may
warrant professional assessment") rather than diagnostic claims, and always
records which model/version produced the result.

Load-handling note: the `process_*_background` wrappers at the bottom of
this file are what the API layer actually schedules (via FastAPI
`BackgroundTasks`) instead of calling `run_*_assessment` directly in the
request. This matters a lot on a resource-constrained instance (e.g.
Render's free tier: 0.1 CPU / 512MB RAM) — the HTTP response returns
immediately with status "pending" instead of holding the connection (and
blocking that worker) for the whole duration of the analysis, so one
person's video upload doesn't stall every other request being served by
the same process. This isn't a substitute for a real task queue
(Celery/RQ) at high sustained volume, but it's a genuine, real improvement
over fully synchronous processing for moderate concurrent load, achieved
without adding any new infrastructure (no Redis/worker service needed).

Each `process_*_background` function opens its OWN database session
rather than reusing the request's session, because the request's session
is closed as soon as the response is sent — a background task that runs
after that point must not touch it.
"""
import json
import logging

from sqlalchemy.orm import Session

from app.db import session as db_session
from app.models.assessments import AnalysisResult, Assessment, MediaFile
from app.models.therapy import Notification
from app.services.audio_analysis import (
    AudioFeatureExtractor,
    assess_input_quality,
    get_speech_to_text_model,
)
from app.services.fluency_analysis import FluencyPatternDetector, get_stuttering_classifier
from app.services.image_analysis import get_image_analysis_model
from app.services.knowledge_base_service import retrieve
from app.services.pronunciation_analysis import analyze_pronunciation, estimate_asr_reliability
from app.services.storage import get_storage_backend

logger = logging.getLogger(__name__)

_extractor = AudioFeatureExtractor()
_stt_model = get_speech_to_text_model()
_fluency_detector = FluencyPatternDetector()


def run_audio_assessment(db: Session, assessment: Assessment, media_file: MediaFile) -> AnalysisResult:
    assessment.status = "processing"
    db.add(assessment)
    db.commit()

    storage = get_storage_backend()
    resolved_path = str(storage.path_for(media_file.storage_path))

    try:
        features = _extractor.extract(resolved_path)
    except Exception as exc:  # noqa: BLE001
        assessment.status = "failed"
        db.add(assessment)
        db.commit()
        raise

    quality_score, quality_issues = assess_input_quality(features)

    transcription = _stt_model.transcribe(resolved_path, assessment.language)
    fluency = _fluency_detector.analyze(resolved_path)

    stuttering_classifier = get_stuttering_classifier()
    stuttering_result = stuttering_classifier.classify(resolved_path) if stuttering_classifier else None

    pronunciation_result = None
    if assessment.reference_text:
        pronunciation_result = analyze_pronunciation(
            reference_text=assessment.reference_text,
            recognized_text=transcription.get("text") or "",
            asr_reliability=estimate_asr_reliability(_stt_model.name),
        )

    limitations = [
        "This is an AI-assisted screening tool, not a clinical diagnosis.",
        "A single recording is not sufficient for a reliable clinical picture.",
    ]
    if stuttering_result and stuttering_result.available:
        limitations.append(stuttering_result.note)
    else:
        limitations.append(
            "No trained disorder-specific classifier is available in this "
            "deployment — fluency indicators below are unvalidated signal-"
            "processing heuristics (candidate patterns only), not a validated "
            "clinical score. Set HF_API_TOKEN to enable the real trained "
            "stuttering classifier. See the fluency section for details."
        )
    if transcription["available"]:
        limitations.append(f"Transcript note: {transcription['note']}")
    else:
        limitations.append(f"Transcript unavailable: {transcription['note']}")
    if pronunciation_result:
        limitations.append(f"Pronunciation analysis: {pronunciation_result.note}")
    if quality_issues:
        limitations.extend(quality_issues)

    summary_parts = [
        f"Recording duration: {features.duration_seconds}s.",
        f"Estimated speaking-voiced ratio: {features.speaking_rate_estimate * 100:.0f}%.",
        f"Detected {features.pause_count} pause segment(s) longer than 300ms.",
    ]
    if features.pitch_mean_hz is not None:
        summary_parts.append(f"Mean pitch (voiced frames): {features.pitch_mean_hz} Hz.")
    else:
        summary_parts.append("No stable voiced pitch was detected in this recording.")
    if transcription["available"] and transcription["text"]:
        summary_parts.append(f'Rough transcript (low-confidence, offline ASR): "{transcription["text"]}".')
    if pronunciation_result and pronunciation_result.available:
        summary_parts.append(
            f"Pronunciation comparison against reference text: "
            f"{pronunciation_result.accuracy * 100:.0f}% word-level match."
        )
    if stuttering_result and stuttering_result.available:
        top_scores = sorted(stuttering_result.label_scores.items(), key=lambda x: x[1], reverse=True)[:3]
        scores_str = ", ".join(f"{label}: {score*100:.0f}%" for label, score in top_scores)
        summary_parts.append(
            f"Stuttering-event classifier (trained model, SEP-28k-based): "
            f"most likely category is '{stuttering_result.predicted_label}' ({scores_str}). "
            "A trained-model screening signal, not a diagnosis."
        )
    elif fluency.analyzed_frames > 0:
        summary_parts.append(
            f"Fluency screening (heuristic, unvalidated): "
            f"{fluency.repetition_candidate_count} repetition-like pattern(s), "
            f"{fluency.prolongation_candidate_count} prolongation-like pattern(s), "
            f"{fluency.abrupt_cutoff_count} abrupt-cutoff pattern(s) detected. "
            "These are candidate acoustic patterns for specialist review, not a diagnosis."
        )
    summary_parts.append(
        "These are raw acoustic measurements only; the platform does not diagnose a "
        "disorder from this data. A professional assessment is recommended for any "
        "concerns about fluency, articulation, or voice."
    )

    features_dict = features.to_dict()
    features_dict["transcript"] = transcription["text"]
    features_dict["transcript_model"] = _stt_model.name
    features_dict["transcript_available"] = transcription["available"]
    features_dict["fluency_indicators"] = fluency.to_dict()
    features_dict["stuttering_classification"] = stuttering_result.to_dict() if stuttering_result else None
    features_dict["pronunciation"] = pronunciation_result.to_dict() if pronunciation_result else None

    result = AnalysisResult(
        assessment_id=assessment.id,
        model_name=_extractor.name,
        model_version=_extractor.version,
        features_json=json.dumps(features_dict),
        input_quality_score=quality_score,
        limitations="\n".join(limitations),
        summary=" ".join(summary_parts),
    )
    db.add(result)

    assessment.status = "completed"
    db.add(assessment)
    db.add(
        Notification(
            user_id=assessment.user_id,
            notification_type="assessment_completed",
            title="Assessment completed",
            message="Your speech assessment has finished processing. View the results now.",
        )
    )
    db.commit()
    db.refresh(result)
    return result


def run_video_assessment(db: Session, assessment: Assessment, media_file: MediaFile) -> AnalysisResult:
    """Real multimodal fusion (spec sections 29-30): extracts and analyzes
    the actual audio track and sampled frames from the uploaded video."""
    from app.services.video_analysis import analyze_video

    assessment.status = "processing"
    db.add(assessment)
    db.commit()

    storage = get_storage_backend()
    resolved_path = str(storage.path_for(media_file.storage_path))

    try:
        analysis = analyze_video(resolved_path)
    except Exception:
        assessment.status = "failed"
        db.add(assessment)
        db.commit()
        raise

    limitations = [
        "This is an AI-assisted screening tool, not a clinical diagnosis.",
        analysis["video_summary"]["note"],
        "No trained disorder-specific classifier is available in this deployment.",
    ]
    if analysis["audio_result"] is None:
        limitations.append("No audio track was found or could be extracted from this video.")
    if analysis["video_summary"]["frames_sampled"] == 0:
        limitations.append("No video frames could be sampled from this file.")

    summary_parts = [f"Video duration: {analysis['video_summary']['duration_seconds']}s."]
    if analysis["audio_result"]:
        af = analysis["audio_result"]["features"]
        summary_parts.append(
            "Audio track analyzed — "
            + (f"pitch: {af['pitch_mean_hz']} Hz." if af["pitch_mean_hz"] else "no stable pitch detected.")
        )
        if analysis["fluency_result"]:
            fr = analysis["fluency_result"]
            summary_parts.append(
                f"Fluency screening (heuristic): {fr['repetition_candidate_count']} repetition-like, "
                f"{fr['prolongation_candidate_count']} prolongation-like pattern(s)."
            )
    faces = analysis["video_summary"]["faces_detected_in_frames"]
    frames = analysis["video_summary"]["frames_sampled"]
    summary_parts.append(f"Face detected in {faces} of {frames} sampled frame(s).")
    summary_parts.append("This does not diagnose any communication, developmental, or medical condition.")

    result = AnalysisResult(
        assessment_id=assessment.id,
        model_name="video-fusion-pipeline",
        model_version="1.0",
        features_json=json.dumps(analysis),
        input_quality_score=1.0 if (analysis["audio_result"] and frames > 0) else 0.5,
        limitations="\n".join(limitations),
        summary=" ".join(summary_parts),
    )
    db.add(result)

    assessment.status = "completed"
    db.add(assessment)
    db.add(
        Notification(
            user_id=assessment.user_id,
            notification_type="assessment_completed",
            title="Assessment completed",
            message="Your video assessment has finished processing. View the results now.",
        )
    )
    db.commit()
    db.refresh(result)
    return result


def get_supporting_evidence(db: Session, assessment: Assessment, top_k: int = 3) -> list[dict]:
    """Pull relevant Knowledge Base excerpts for the assessment type — used
    to populate the "Why this result?" / evidence panel (spec section 96)."""
    query = f"{assessment.assessment_type} speech assessment fluency pronunciation voice"
    return retrieve(db, query, top_k=top_k)


def build_unified_result(db: Session, assessment: Assessment) -> dict:
    """Assemble the Unified Assessment Result (spec section 15) — one
    consistent JSON shape across audio/image/video assessments, so the
    frontend never needs type-specific branching to render a result:

        assessment_id, status, input_quality, transcription, fluency,
        stuttering, pronunciation, audio_features, visual_observations,
        evidence, models, limitations

    Every field defaults to null/empty rather than a fabricated value when
    that assessment type didn't produce it (e.g. `visual_observations` is
    always null for a pure audio assessment) — presence of a field never
    implies a claim that wasn't actually computed."""
    result = assessment.analysis_result
    base = {
        "assessment_id": str(assessment.id),
        "status": assessment.status,
        "assessment_type": assessment.assessment_type,
        "review_status": assessment.review_status,
        "input_quality": None,
        "transcription": None,
        "fluency": None,
        "stuttering": None,
        "pronunciation": None,
        "audio_features": None,
        "visual_observations": None,
        "evidence": [],
        "models": [],
        "limitations": [],
        "summary": None,
    }
    if result is None:
        return base

    try:
        features = json.loads(result.features_json)
    except (json.JSONDecodeError, TypeError):
        features = {}

    base["input_quality"] = {"score": result.input_quality_score}
    base["summary"] = result.summary
    base["limitations"] = [line for line in result.limitations.split("\n") if line]
    base["models"] = [{"name": result.model_name, "version": result.model_version}]

    if assessment.assessment_type == "audio":
        base["transcription"] = {
            "text": features.get("transcript"),
            "available": features.get("transcript_available"),
            "model": features.get("transcript_model"),
            # Evidence label per spec section 13: this comes entirely from
            # the audio track.
            "evidence_source": "audio",
        }
        base["fluency"] = features.get("fluency_indicators")
        base["stuttering"] = features.get("stuttering_classification")
        base["pronunciation"] = features.get("pronunciation")
        base["audio_features"] = {
            k: v
            for k, v in features.items()
            if k not in ("transcript", "transcript_available", "transcript_model", "fluency_indicators", "stuttering_classification", "pronunciation")
        }
        for section in ("fluency", "stuttering", "pronunciation", "audio_features"):
            if base[section] is not None:
                base[section]["evidence_source"] = "audio" if section != "audio_features" else base[section].get("evidence_source", "audio")

    elif assessment.assessment_type == "video":
        audio_result = features.get("audio_result")
        base["transcription"] = (
            {**(audio_result.get("transcription") or {}), "evidence_source": "audio"} if audio_result else None
        )
        base["fluency"] = {**features["fluency_result"], "evidence_source": "audio"} if features.get("fluency_result") else None
        base["audio_features"] = (
            {**audio_result["features"], "evidence_source": "audio"} if audio_result and audio_result.get("features") else None
        )
        base["visual_observations"] = (
            {**features["video_summary"], "evidence_source": "visual"} if features.get("video_summary") else None
        )
        # This assessment type combines both — label it explicitly (spec
        # section 13: "Improve the UI so the user understands which
        # evidence came from: Audio / Visual / Combined").
        if base["audio_features"] and base["visual_observations"]:
            base["combined_evidence_note"] = (
                "This result combines independently-computed audio-track "
                "evidence and visual (frame-sampled) evidence — see each "
                "section's evidence_source."
            )

    elif assessment.assessment_type == "image":
        base["visual_observations"] = {**features, "evidence_source": "visual"}

    base["evidence"] = get_supporting_evidence(db, assessment)
    return base


def run_image_assessment(db: Session, assessment: Assessment, media_file: MediaFile) -> AnalysisResult:
    """Real image analysis (spec section 28). Per spec, this NEVER infers a
    syndrome or disorder from appearance — only descriptive/geometric
    observations, always with a specialist-review disclaimer."""
    assessment.status = "processing"
    db.add(assessment)
    db.commit()

    storage = get_storage_backend()
    resolved_path = str(storage.path_for(media_file.storage_path))

    model = get_image_analysis_model()
    try:
        analysis = model.analyze(resolved_path)
    except Exception:
        assessment.status = "failed"
        db.add(assessment)
        db.commit()
        raise

    limitations = [
        "This is a descriptive/geometric image analysis, not a clinical assessment.",
        "The system never infers a syndrome, disorder, or diagnosis from an "
        "image or appearance alone — only observable, descriptive features.",
        analysis.note,
    ]

    summary_parts = [
        f"Face detected: {'yes' if analysis.face_detected else 'no'}"
        + (f" ({analysis.face_count} face region(s))." if analysis.face_detected else "."),
    ]
    if analysis.face_detected:
        if analysis.symmetry_score is not None:
            summary_parts.append(f"Rough bounding-box symmetry score: {analysis.symmetry_score:.2f} (0-1).")
        summary_parts.append(f"Eye regions detected: {analysis.eyes_detected}.")
    if analysis.description:
        summary_parts.append(f"Descriptive observation: {analysis.description}")
    summary_parts.append(
        "This does not diagnose any communication, developmental, or medical condition."
    )

    result = AnalysisResult(
        assessment_id=assessment.id,
        model_name=model.name,
        model_version="1.0",
        features_json=json.dumps(analysis.to_dict()),
        input_quality_score=1.0 if analysis.face_detected else 0.3,
        limitations="\n".join(limitations),
        summary=" ".join(summary_parts),
    )
    db.add(result)

    assessment.status = "completed"
    db.add(assessment)
    db.add(
        Notification(
            user_id=assessment.user_id,
            notification_type="assessment_completed",
            title="Assessment completed",
            message="Your image assessment has finished processing. View the results now.",
        )
    )
    db.commit()
    db.refresh(result)
    return result


# --- Background-task entry points (see module docstring) -------------------

_RUNNERS = {
    "audio": run_audio_assessment,
    "image": run_image_assessment,
    "video": run_video_assessment,
}


def _mark_failed(db: Session, assessment_id: str, reason: str) -> None:
    """Mark an assessment failed and tell the user. Rolls back first: if the
    failure was a DB error the session is unusable until rolled back, and the
    status update itself would otherwise raise and leave the assessment stuck
    on 'processing' forever."""
    db.rollback()
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        return
    assessment.status = "failed"
    db.add(assessment)
    db.add(
        Notification(
            user_id=assessment.user_id,
            notification_type="assessment_failed",
            title="Assessment could not be processed",
            message=(
                "We couldn't analyze your file. Please check that it is a valid, "
                "uncorrupted recording/image/video and try again."
            ),
        )
    )
    db.commit()
    logger.warning("Assessment %s marked failed: %s", assessment_id, reason)


def process_assessment_background(assessment_id: str, media_file_id: str, assessment_type: str) -> None:
    """Scheduled via FastAPI BackgroundTasks from the API layer. Opens its
    own DB session (the request's session is already closed by the time
    this runs) and marks the assessment 'failed' if anything raises,
    rather than leaving it stuck on 'pending' forever."""
    db = db_session.SessionLocal()
    try:
        assessment = db.get(Assessment, assessment_id)
        media = db.get(MediaFile, media_file_id)
        if assessment is None or media is None:
            return

        runner = _RUNNERS.get(assessment_type)
        if runner is None:
            _mark_failed(db, assessment_id, f"unsupported assessment type '{assessment_type}'")
            return

        try:
            runner(db, assessment, media)
        except Exception:  # noqa: BLE001
            logger.exception("Assessment %s (%s) failed during processing", assessment_id, assessment_type)
            _mark_failed(db, assessment_id, "processing error")
    finally:
        db.close()
