from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.disorders import Disorder, DisorderCategory, Syndrome
from app.models.user import User
from app.schemas.disorders import (
    DisorderCategoryCreate,
    DisorderCategoryOut,
    DisorderCategoryUpdate,
    DisorderCreate,
    DisorderOut,
    DisorderProfileDraft,
    DisorderUpdate,
    SyndromeCreate,
    SyndromeOut,
    SyndromeUpdate,
)
from app.security.dependencies import assert_can_view_inactive, get_optional_user, require_permission
from app.security.rate_limit import rate_limit_ai
from app.services import knowledge_base_service, llm
from app.services.audit_service import log_event
from app.services.storage import ALLOWED_DOCUMENT_EXTENSIONS, get_storage_backend, validate_upload

router = APIRouter(prefix="/disorders", tags=["Disorders & Syndromes"])


@router.get("/categories", response_model=list[DisorderCategoryOut])
def list_categories(db: Session = Depends(get_db)):
    return db.scalars(select(DisorderCategory)).all()


@router.post("/categories", response_model=DisorderCategoryOut, status_code=201)
def create_category(
    data: DisorderCategoryCreate,
    db: Session = Depends(get_db),
    _admin=Depends(require_permission("manage_disorders")),
):
    category = DisorderCategory(**data.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.patch("/categories/{category_id}", response_model=DisorderCategoryOut)
def update_category(
    category_id: str,
    data: DisorderCategoryUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(require_permission("manage_disorders")),
):
    category = db.get(DisorderCategory, category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(category, field, value)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.get("", response_model=list[DisorderOut])
def list_disorders(
    category_id: str | None = None,
    language: str | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    if include_inactive:
        assert_can_view_inactive(viewer, "manage_disorders")
    stmt = select(Disorder)
    if not include_inactive:
        stmt = stmt.where(Disorder.is_active.is_(True))
    if category_id:
        stmt = stmt.where(Disorder.category_id == category_id)
    if language:
        stmt = stmt.where(Disorder.language == language)
    return db.scalars(stmt).all()


@router.get("/syndromes", response_model=list[SyndromeOut])
def list_syndromes(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    if include_inactive:
        assert_can_view_inactive(viewer, "manage_disorders")
    stmt = select(Syndrome)
    if not include_inactive:
        stmt = stmt.where(Syndrome.is_active.is_(True))
    return db.scalars(stmt).all()


@router.post("/syndromes", response_model=SyndromeOut, status_code=201)
def create_syndrome(
    data: SyndromeCreate,
    db: Session = Depends(get_db),
    _admin=Depends(require_permission("manage_disorders")),
):
    existing = db.scalar(select(Syndrome).where(Syndrome.slug == data.slug))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already exists")
    syndrome = Syndrome(**data.model_dump())
    db.add(syndrome)
    db.commit()
    db.refresh(syndrome)
    return syndrome


@router.patch("/syndromes/{syndrome_id}", response_model=SyndromeOut)
def update_syndrome(
    syndrome_id: str,
    data: SyndromeUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(require_permission("manage_disorders")),
):
    syndrome = db.get(Syndrome, syndrome_id)
    if syndrome is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Syndrome not found")
    updates = data.model_dump(exclude_unset=True)
    if "slug" in updates and updates["slug"] != syndrome.slug:
        clash = db.scalar(select(Syndrome).where(Syndrome.slug == updates["slug"]))
        if clash:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already exists")
    for field, value in updates.items():
        setattr(syndrome, field, value)
    db.add(syndrome)
    db.commit()
    db.refresh(syndrome)
    return syndrome


@router.post(
    "/extract-from-document",
    response_model=DisorderProfileDraft,
    dependencies=[Depends(rate_limit_ai)],
)
async def extract_disorder_profile_from_document(
    file: UploadFile = File(...),
    _admin: User = Depends(require_permission("manage_disorders")),
):
    """AI-assisted content-authoring aid (spec: admin content management).
    Uploads a reference document (PDF/DOCX/TXT/MD) and returns a DRAFT
    disorder profile for the admin to review and edit — nothing is ever
    saved automatically. Requires OPENAI_API_KEY; returns an honest
    'unavailable' response otherwise rather than fabricating a draft."""
    content = await file.read()
    ext = validate_upload(file, ALLOWED_DOCUMENT_EXTENSIONS, content)

    storage = get_storage_backend()
    storage_path = storage.save("disorder_extraction_temp", file.filename, content)
    full_path = storage.path_for(storage_path)

    try:
        text = knowledge_base_service.extract_text(str(full_path), ext)
    except Exception as exc:  # noqa: BLE001
        storage.delete(storage_path)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to extract text from document: {exc}",
        )

    storage.delete(storage_path)  # this is a scratch upload for extraction only, not a KB document

    if not text.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No extractable text found in document.")

    draft = llm.extract_disorder_profile(text)
    return DisorderProfileDraft(**draft)


@router.get("/{slug}", response_model=DisorderOut)
def get_disorder(slug: str, db: Session = Depends(get_db)):
    disorder = db.scalar(select(Disorder).where(Disorder.slug == slug))
    if disorder is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Disorder not found")
    return disorder


@router.post("", response_model=DisorderOut, status_code=201)
def create_disorder(
    data: DisorderCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_permission("manage_disorders")),
):
    existing = db.scalar(select(Disorder).where(Disorder.slug == data.slug))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already exists")
    disorder = Disorder(**data.model_dump())
    db.add(disorder)
    db.commit()
    db.refresh(disorder)
    log_event(db, action="disorder.create", user_id=str(admin.id), resource_type="disorder", resource_id=str(disorder.id))
    return disorder


@router.patch("/{disorder_id}", response_model=DisorderOut)
def update_disorder(
    disorder_id: str,
    data: DisorderUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_permission("manage_disorders")),
):
    disorder = db.get(Disorder, disorder_id)
    if disorder is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Disorder not found")
    updates = data.model_dump(exclude_unset=True)
    if "slug" in updates and updates["slug"] != disorder.slug:
        clash = db.scalar(select(Disorder).where(Disorder.slug == updates["slug"]))
        if clash:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already exists")
    for field, value in updates.items():
        setattr(disorder, field, value)
    db.add(disorder)
    db.commit()
    db.refresh(disorder)
    log_event(db, action="disorder.update", user_id=str(admin.id), resource_type="disorder", resource_id=disorder_id)
    return disorder
