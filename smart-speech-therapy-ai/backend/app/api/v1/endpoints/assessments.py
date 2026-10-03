from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.assessments import Assessment, MediaFile
from app.models.user import User
from app.schemas.assessments import (
    AssessmentCreate,
    AssessmentOut,
    AssessmentReviewRequest,
    MediaFileOut,
)
from app.security.dependencies import get_current_active_user, require_roles
from app.services import assessment_service
from app.services.storage import (
    ALLOWED_AUDIO_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_VIDEO_EXTENSIONS,
    get_storage_backend,
    validate_upload,
)

router = APIRouter(prefix="/assessments", tags=["Assessments"])


def _upload_media(file: UploadFile, content: bytes, media_type: str, subdir: str, allowed_ext: set, db: Session, user: User) -> MediaFile:
    validate_upload(file, allowed_ext, content)
    storage = get_storage_backend()
    storage_path = storage.save(subdir, file.filename, content)

    media = MediaFile(
        user_id=user.id,
        media_type=media_type,
        original_filename=file.filename,
        storage_path=storage_path,
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


@router.post("/media/audio", response_model=MediaFileOut, status_code=201)
async def upload_audio(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    content = await file.read()
    return _upload_media(file, content, "audio", "audio", ALLOWED_AUDIO_EXTENSIONS, db, current_user)


@router.post("/media/image", response_model=MediaFileOut, status_code=201)
async def upload_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    content = await file.read()
    return _upload_media(file, content, "image", "images", ALLOWED_IMAGE_EXTENSIONS, db, current_user)


@router.post("/media/video", response_model=MediaFileOut, status_code=201)
async def upload_video(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    content = await file.read()
    return _upload_media(file, content, "video", "videos", ALLOWED_VIDEO_EXTENSIONS, db, current_user)


@router.post("", response_model=AssessmentOut, status_code=201)
def create_assessment(
    data: AssessmentCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not current_user.has_permission("create_assessment"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing permission: create_assessment")

    media = db.get(MediaFile, data.media_file_id)
    if media is None or str(media.user_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found")
    if data.assessment_type in ("audio", "image", "video") and media.media_type != data.assessment_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Media file is type '{media.media_type}', not '{data.assessment_type}'",
        )

    assessment = Assessment(
        user_id=current_user.id,
        media_file_id=media.id,
        assessment_type=data.assessment_type,
        language=data.language,
        status="pending",
        reference_text=data.reference_text,
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)

    # Scheduled to run AFTER this response is sent, in a worker thread —
    # the request returns immediately with status "pending" instead of
    # blocking on the analysis. See assessment_service's module docstring
    # for why this matters on a resource-constrained instance. The
    # frontend polls GET /assessments/{id} until status changes.
    background_tasks.add_task(
        assessment_service.process_assessment_background,
        str(assessment.id),
        str(media.id),
        data.assessment_type,
    )

    return assessment


@router.get("/me", response_model=list[AssessmentOut])
def my_assessments(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    return db.scalars(select(Assessment).where(Assessment.user_id == current_user.id)).all()


@router.get("/pending-review", response_model=list[AssessmentOut])
def pending_review_assessments(
    db: Session = Depends(get_db),
    _viewer: User = Depends(require_roles("SPECIALIST", "ADMIN")),
):
    """Assessment review queue (spec section 25: Specialist Dashboard ->
    Assessments / AI Findings). Must be registered before the
    '/{assessment_id}' route below — otherwise FastAPI would try to parse
    the literal string 'pending-review' as an assessment id and 404."""
    return db.scalars(
        select(Assessment)
        .where(Assessment.review_status == "unreviewed", Assessment.status == "completed")
        .order_by(Assessment.created_at.asc())
    ).all()


@router.get("/{assessment_id}", response_model=AssessmentOut)
def get_assessment(
    assessment_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)
):
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    is_owner = str(assessment.user_id) == str(current_user.id)
    if not is_owner and not current_user.has_permission("review_assessment"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this assessment")
    return assessment


@router.get("/{assessment_id}/evidence")
def get_evidence(
    assessment_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)
):
    """'Why this result?' Knowledge Base evidence panel (spec section 96)."""
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    is_owner = str(assessment.user_id) == str(current_user.id)
    if not is_owner and not current_user.has_permission("review_assessment"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this assessment")
    return {"excerpts": assessment_service.get_supporting_evidence(db, assessment)}


@router.get("/{assessment_id}/result")
def get_unified_result(
    assessment_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)
):
    """The Unified Assessment Result (spec section 15): one consistent JSON
    shape across audio/image/video assessments — see
    assessment_service.build_unified_result() for the exact contract."""
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    is_owner = str(assessment.user_id) == str(current_user.id)
    if not is_owner and not current_user.has_permission("review_assessment"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this assessment")
    return assessment_service.build_unified_result(db, assessment)


@router.post("/{assessment_id}/review", response_model=AssessmentOut)
def review_assessment(
    assessment_id: str,
    data: AssessmentReviewRequest,
    db: Session = Depends(get_db),
    current_specialist: User = Depends(require_roles("SPECIALIST", "ADMIN")),
):
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    assessment.review_status = "approved" if data.approve else "rejected"
    assessment.reviewed_by_id = current_specialist.id
    assessment.reviewer_notes = data.notes
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return assessment
