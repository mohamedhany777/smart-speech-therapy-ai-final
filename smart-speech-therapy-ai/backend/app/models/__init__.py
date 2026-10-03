"""
Import every model module here so:
  1. `Base.metadata` is fully populated for Alembic autogenerate.
  2. SQLAlchemy relationship string lookups ("User", "Role", ...) resolve.

New domain modules (disorders, assessments, exercises, games, knowledge
base, etc.) should be added as their own files under app/models/ and
imported here — see spec section 62 for the full target schema. This
scaffold implements the auth/RBAC core fully; the remaining entities are
the next slice of work.
"""
from app.db.session import Base  # noqa: F401
from app.models.rbac import Role, Permission  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.auth import RefreshToken, AuditLog  # noqa: F401
from app.models.profiles import PatientProfile, SpecialistProfile  # noqa: F401
from app.models.disorders import DisorderCategory, Disorder, Syndrome  # noqa: F401
from app.models.knowledge_base import KnowledgeDocument, DocumentChunk, WebSource  # noqa: F401
from app.models.exercises import Exercise, ExerciseCompletion  # noqa: F401
from app.models.games import Game, GameSession  # noqa: F401
from app.models.assessments import MediaFile, Assessment, AnalysisResult  # noqa: F401
from app.models.therapy import TherapyPlan, TherapyPlanItem, Notification  # noqa: F401

__all__ = [
    "Base",
    "Role",
    "Permission",
    "User",
    "RefreshToken",
    "AuditLog",
    "PatientProfile",
    "SpecialistProfile",
    "DisorderCategory",
    "Disorder",
    "Syndrome",
    "KnowledgeDocument",
    "DocumentChunk",
    "WebSource",
    "Exercise",
    "ExerciseCompletion",
    "Game",
    "GameSession",
    "MediaFile",
    "Assessment",
    "AnalysisResult",
    "TherapyPlan",
    "TherapyPlanItem",
    "Notification",
]
