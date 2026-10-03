from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.exercises import Exercise, ExerciseCompletion
from app.models.user import User
from app.schemas.exercises import (
    ExerciseCompletionCreate,
    ExerciseCompletionOut,
    ExerciseCreate,
    ExerciseOut,
    ExerciseUpdate,
)
from app.security.dependencies import (
    assert_can_view_inactive,
    get_current_active_user,
    get_optional_user,
    require_permission,
)
from app.services.audit_service import log_event

router = APIRouter(prefix="/exercises", tags=["Exercises"])


@router.get("", response_model=list[ExerciseOut])
def list_exercises(
    category: str | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    if include_inactive:
        assert_can_view_inactive(viewer, "manage_exercises")
    stmt = select(Exercise)
    if not include_inactive:
        stmt = stmt.where(Exercise.is_active.is_(True))
    if category:
        stmt = stmt.where(Exercise.category == category)
    return db.scalars(stmt).all()


@router.post("", response_model=ExerciseOut, status_code=201)
def create_exercise(
    data: ExerciseCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_permission("manage_exercises")),
):
    exercise = Exercise(**data.model_dump())
    db.add(exercise)
    db.commit()
    db.refresh(exercise)
    log_event(db, action="exercise.create", user_id=str(admin.id), resource_type="exercise", resource_id=str(exercise.id))
    return exercise


@router.patch("/{exercise_id}", response_model=ExerciseOut)
def update_exercise(
    exercise_id: str,
    data: ExerciseUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_permission("manage_exercises")),
):
    exercise = db.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exercise not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(exercise, field, value)
    db.add(exercise)
    db.commit()
    db.refresh(exercise)
    log_event(db, action="exercise.update", user_id=str(admin.id), resource_type="exercise", resource_id=exercise_id)
    return exercise


@router.post("/{exercise_id}/complete", response_model=ExerciseCompletionOut, status_code=201)
def complete_exercise(
    exercise_id: str,
    data: ExerciseCompletionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not current_user.has_permission("complete_exercises"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing permission: complete_exercises")

    exercise = db.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exercise not found")

    completion = ExerciseCompletion(
        exercise_id=exercise.id, user_id=current_user.id, score=data.score, notes=data.notes
    )
    db.add(completion)
    db.commit()
    db.refresh(completion)
    return completion


@router.get("/me/history", response_model=list[ExerciseCompletionOut])
def my_exercise_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return db.scalars(
        select(ExerciseCompletion).where(ExerciseCompletion.user_id == current_user.id)
    ).all()
