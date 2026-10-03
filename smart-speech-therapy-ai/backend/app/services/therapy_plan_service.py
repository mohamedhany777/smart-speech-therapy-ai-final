"""
Personalized support plan generation (spec sections 34-35, 94).

Plans are always created with status "ai_draft" and MUST be reviewed by a
specialist before being considered final — the API layer never exposes a
draft plan as an approved one. Exercise selection is a transparent
rule-based match on category + computed audio features, not a black-box
model, so the "why this recommendation" reasoning is always inspectable.
"""
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.assessments import AnalysisResult, Assessment
from app.models.exercises import Exercise
from app.models.therapy import Notification, TherapyPlan, TherapyPlanItem

# Simple, documented feature -> exercise-category rules. A production system
# would refine these thresholds with clinical input; nothing here is dressed
# up as a trained model's output.
FEATURE_RULES = [
    ("pause_count", lambda v: v is not None and v >= 5, "fluency"),
    ("speaking_rate_estimate", lambda v: v is not None and v < 0.3, "fluency"),
    ("silence_ratio", lambda v: v is not None and v > 0.6, "voice"),
]


def _flatten_features(features: dict) -> dict:
    """Video assessments nest the audio-track features under
    audio_result.features; lift them so the same rules apply to both."""
    audio = features.get("audio_result")
    if isinstance(audio, dict) and isinstance(audio.get("features"), dict):
        return {**audio["features"], **{k: v for k, v in features.items() if k != "audio_result"}}
    return features


def _recommended_categories(features: dict) -> list[str]:
    features = _flatten_features(features)
    categories = []
    for feature_key, predicate, category in FEATURE_RULES:
        if predicate(features.get(feature_key)):
            categories.append(category)
    if not categories:
        categories.append("communication")  # sensible general default
    return list(dict.fromkeys(categories))  # de-dupe, keep order


def generate_draft_plan(db: Session, assessment: Assessment) -> TherapyPlan:
    # Idempotent: clicking "Generate plan" twice must not create duplicate
    # drafts. A rejected plan may be regenerated.
    existing = db.scalar(
        select(TherapyPlan).where(
            TherapyPlan.assessment_id == assessment.id, TherapyPlan.status != "rejected"
        )
    )
    if existing is not None:
        return existing

    result = db.scalar(
        select(AnalysisResult).where(AnalysisResult.assessment_id == assessment.id)
    )
    features = json.loads(result.features_json) if result else {}
    categories = _recommended_categories(features)

    plan = TherapyPlan(
        user_id=assessment.user_id,
        assessment_id=assessment.id,
        status="ai_draft",
        duration_weeks=8,
        sessions_per_week=3,
        goals=(
            "AI-suggested focus areas based on this assessment's acoustic "
            f"features: {', '.join(categories)}. A specialist must review "
            "and approve this plan before it is considered final."
        ),
    )
    db.add(plan)
    db.flush()

    exercises = db.scalars(
        select(Exercise).where(Exercise.category.in_(categories), Exercise.is_active.is_(True)).limit(6)
    ).all()

    for ex in exercises:
        db.add(
            TherapyPlanItem(
                plan_id=plan.id,
                item_type="exercise",
                exercise_id=ex.id,
                frequency="3x/week",
                notes=f"Recommended for category: {ex.category}",
            )
        )

    db.commit()
    db.refresh(plan)
    return plan


def review_plan(db: Session, plan: TherapyPlan, approve: bool, reviewer_id: str, notes: str | None) -> TherapyPlan:
    plan.status = "approved" if approve else "rejected"
    plan.reviewed_by_id = reviewer_id
    plan.reviewer_notes = notes
    db.add(plan)
    db.add(
        Notification(
            user_id=plan.user_id,
            notification_type="therapy_plan_reviewed",
            title="Your support plan was reviewed",
            message=(
                f"A specialist {'approved' if approve else 'rejected'} your support plan."
                + (f" Notes: {notes}" if notes else "")
            ),
        )
    )
    db.commit()
    db.refresh(plan)
    return plan
