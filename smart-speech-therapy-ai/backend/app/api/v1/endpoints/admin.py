"""
Example admin-only routes demonstrating role + permission enforcement.
Real admin functionality (user management, KB management, model management,
etc. from spec sections 44-46) plugs into this router as it's built out.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import UserOut
from app.security.dependencies import require_permission, require_roles
from app.services import audit_service
from app.services.model_registry import get_registry

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/users", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _current_admin=Depends(require_roles("ADMIN")),
):
    users = db.scalars(select(User)).all()
    return [UserOut.from_model(u) for u in users]


@router.get("/audit-logs")
def list_audit_logs(
    limit: int = 100,
    db: Session = Depends(get_db),
    _admin=Depends(require_permission("view_audit_logs")),
):
    from app.models.auth import AuditLog

    logs = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500))).all()
    return [
        {
            "id": str(log.id),
            "user_id": str(log.user_id) if log.user_id else None,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]


@router.get("/analytics")
def system_analytics(
    db: Session = Depends(get_db),
    _admin=Depends(require_permission("view_system_analytics")),
):
    """Real counts from the database — spec section 80. Not projected or
    estimated figures; every number here is a live COUNT(*) query."""
    from sqlalchemy import func

    from app.models.assessments import Assessment
    from app.models.exercises import ExerciseCompletion
    from app.models.games import GameSession
    from app.models.knowledge_base import DocumentChunk, KnowledgeDocument
    from app.models.therapy import TherapyPlan

    def count(model) -> int:
        return db.scalar(select(func.count()).select_from(model)) or 0

    return {
        "total_users": count(User),
        "active_users": db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))) or 0,
        "total_assessments": count(Assessment),
        "completed_assessments": db.scalar(
            select(func.count()).select_from(Assessment).where(Assessment.status == "completed")
        )
        or 0,
        "total_knowledge_documents": count(KnowledgeDocument),
        "total_knowledge_chunks": count(DocumentChunk),
        "total_exercise_completions": count(ExerciseCompletion),
        "total_game_sessions": count(GameSession),
        "therapy_plans_pending_review": db.scalar(
            select(func.count()).select_from(TherapyPlan).where(TherapyPlan.status == "ai_draft")
        )
        or 0,
    }


@router.post("/users/{user_id}/deactivate", status_code=204)
def deactivate_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_permission("manage_users")),
):
    """Deactivate a user account and revoke all of their refresh tokens so
    the deactivation takes effect immediately rather than at token expiry."""
    from app.models.auth import RefreshToken

    if current_admin.id == user_id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = False
    db.add(user)
    for token in db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False))):
        token.revoked = True
        db.add(token)
    db.commit()
    audit_service.log_event(
        db,
        action="user.deactivate",
        user_id=str(current_admin.id),
        resource_type="user",
        resource_id=str(user_id),
    )
    return None


@router.get("/models")
def list_model_registry(
    _current_admin: User = Depends(require_permission("manage_models")),
):
    """The centralized AI Model Registry (spec section 34): every model this
    platform can call, with honest, Hub-verified metadata and whether it is
    currently enabled given this deployment's configured credentials.
    Read-only — models are swapped via environment variables, not this API,
    since changing the active model is a deployment-level decision."""
    return [
        {
            "model_name": m.model_name,
            "role": m.role.value,
            "task": m.task,
            "language": m.language,
            "provider": m.provider,
            "version_or_revision": m.version_or_revision,
            "license": m.license,
            "validated": m.validated,
            "validated_note": m.validated_note,
            "limitations": m.limitations,
            "configurable_via": m.configurable_via,
            "is_current_default": m.is_current_default,
            "enabled": m.enabled(),
        }
        for m in get_registry()
    ]
