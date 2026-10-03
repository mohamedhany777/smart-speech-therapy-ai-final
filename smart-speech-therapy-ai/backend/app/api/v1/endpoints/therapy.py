from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.assessments import Assessment
from app.models.therapy import TherapyPlan
from app.models.user import User
from app.schemas.therapy import TherapyPlanOut, TherapyPlanReviewRequest
from app.security.dependencies import get_current_active_user, require_roles
from app.services import therapy_plan_service

router = APIRouter(prefix="/therapy-plans", tags=["Therapy Plans"])


@router.post("/generate/{assessment_id}", response_model=TherapyPlanOut, status_code=201)
def generate_plan(
    assessment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    is_owner = str(assessment.user_id) == str(current_user.id)
    if not is_owner and not current_user.has_role("ADMIN"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    if assessment.status != "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assessment is not completed yet")

    return therapy_plan_service.generate_draft_plan(db, assessment)


@router.get("/me", response_model=list[TherapyPlanOut])
def my_plans(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    return db.scalars(select(TherapyPlan).where(TherapyPlan.user_id == current_user.id)).all()


@router.get("/pending-review", response_model=list[TherapyPlanOut])
def pending_review(
    db: Session = Depends(get_db),
    # ADMIN can see the review queue for operational oversight/analytics,
    # but cannot approve/reject (see review_plan below) — approval must
    # stay with a SPECIALIST (spec section 16: "Admin can manage
    # templates/content but should not replace specialist approval").
    _viewer: User = Depends(require_roles("SPECIALIST", "ADMIN")),
):
    return db.scalars(select(TherapyPlan).where(TherapyPlan.status == "ai_draft")).all()


@router.post("/{plan_id}/review", response_model=TherapyPlanOut)
def review_plan(
    plan_id: str,
    data: TherapyPlanReviewRequest,
    db: Session = Depends(get_db),
    # Deliberately SPECIALIST-only, not ADMIN — clinical approval of a
    # patient's therapy plan is a specialist responsibility that admin
    # privilege must not bypass (spec section 16).
    current_specialist: User = Depends(require_roles("SPECIALIST")),
):
    plan = db.get(TherapyPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Therapy plan not found")
    if plan.status != "ai_draft":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Plan was already {plan.status}")

    return therapy_plan_service.review_plan(db, plan, data.approve, current_specialist.id, data.notes)
