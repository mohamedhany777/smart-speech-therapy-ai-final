from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.knowledge_base import KnowledgeDocument
from app.models.user import User
from app.schemas.knowledge_base import (
    DocumentUpdate,
    KnowledgeDocumentOut,
    RagAnswer,
    RagQuery,
)
from app.security.dependencies import assert_can_view_inactive, get_current_active_user, get_optional_user, require_permission
from app.security.rate_limit import rate_limit_ai
from app.services import audit_service, knowledge_base_service
from app.services.storage import (
    ALLOWED_DOCUMENT_EXTENSIONS,
    get_storage_backend,
    validate_upload,
)

router = APIRouter(prefix="/knowledge-base", tags=["Knowledge Base / RAG"])


def _to_out(document: KnowledgeDocument) -> KnowledgeDocumentOut:
    out = KnowledgeDocumentOut.model_validate(document)
    out.chunk_count = len(document.chunks)
    return out


@router.post("/documents", response_model=KnowledgeDocumentOut, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    author: str | None = Form(None),
    publication_year: int | None = Form(None),
    document_type: str = Form("book"),
    disorder_category: str | None = Form(None),
    language: str = Form("en"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_permission("manage_knowledge_base")),
):
    """Admin-only document upload + ingestion (spec sections 6, 10, 12, 27).
    Only PDF/TXT/MD/DOCX text extraction is implemented in this scaffold.
    Follows the documented pipeline: UPLOADED -> (validate) -> PROCESSING ->
    extract -> chunk -> embed -> index -> INDEXED, or FAILED with a reason
    kept on the record (not silently deleted) so an admin can see why and
    decide whether to retry with a different file."""
    content = await file.read()
    ext = validate_upload(file, ALLOWED_DOCUMENT_EXTENSIONS, content)

    storage = get_storage_backend()
    storage_path = storage.save("knowledge_base", file.filename, content)

    document = KnowledgeDocument(
        title=title,
        author=author,
        publication_year=publication_year,
        document_type=document_type,
        source_type="internal",
        disorder_category=disorder_category,
        language=language,
        original_filename=file.filename,
        storage_path=storage_path,
        uploaded_by_id=current_admin.id,
        status="UPLOADED",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    document.status = "PROCESSING"
    db.add(document)
    db.commit()

    def _mark_failed(reason: str) -> None:
        """Keep the document record (spec section 6 wants FAILED to be a
        visible, inspectable status) but discard the underlying file
        (usually genuinely corrupt/unreadable) and any partial chunks."""
        db.rollback()
        doc = db.get(KnowledgeDocument, document.id)
        if doc is not None:
            for chunk in list(doc.chunks):
                db.delete(chunk)
            doc.status = "FAILED"
            doc.failure_reason = reason[:2000]
            db.add(doc)
            db.commit()
        storage.delete(storage_path)

    full_path = storage.path_for(storage_path)
    try:
        text = knowledge_base_service.extract_text(str(full_path), ext)
    except Exception as exc:  # noqa: BLE001
        _mark_failed(f"Text extraction failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to extract text from document: {exc}",
        )

    try:
        chunk_count = knowledge_base_service.ingest_document_text(db, document, text)
    except Exception as exc:  # noqa: BLE001
        _mark_failed(f"Ingestion/embedding failed: {exc}")
        raise
    if chunk_count == 0:
        _mark_failed("No extractable text found (e.g. a scanned PDF needing OCR, which is not implemented).")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No extractable text found in document (e.g. a scanned PDF needing OCR, which is not implemented).",
        )

    document.status = "INDEXED"
    db.add(document)
    db.commit()
    db.refresh(document)

    audit_service.log_event(
        db,
        action="knowledge_base.document.upload",
        user_id=str(current_admin.id),
        resource_type="knowledge_document",
        resource_id=str(document.id),
        metadata={"title": title, "chunk_count": chunk_count},
    )

    return _to_out(document)


@router.get("/documents", response_model=list[KnowledgeDocumentOut])
def list_documents(
    q: str | None = None,
    disorder_category: str | None = None,
    status_filter: str | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    """Admin search/browse over the Knowledge Base (spec section 6: Search,
    Categories, Source Details). Unpublished (is_active=False) documents are
    only visible to admins passing include_inactive=true — everyone else
    (including anonymous callers browsing the public catalogue) only ever
    sees published documents, matching what RAG retrieval itself can use."""
    if include_inactive:
        assert_can_view_inactive(viewer, "manage_knowledge_base")
    stmt = select(KnowledgeDocument)
    if not include_inactive:
        # The public/default view is "what's actually usable" — published
        # AND successfully indexed. A document stuck in PROCESSING/FAILED
        # never contributed anything to RAG and isn't "unpublished" either
        # (it never got the chance to publish), so it shouldn't clutter the
        # default view any more than it clutters real RAG answers.
        stmt = stmt.where(KnowledgeDocument.is_active.is_(True), KnowledgeDocument.status == "INDEXED")
    if q:
        stmt = stmt.where(KnowledgeDocument.title.ilike(f"%{q}%"))
    if disorder_category:
        stmt = stmt.where(KnowledgeDocument.disorder_category == disorder_category)
    if status_filter:
        stmt = stmt.where(KnowledgeDocument.status == status_filter.upper())
    documents = db.scalars(stmt.order_by(KnowledgeDocument.created_at.desc())).all()
    return [_to_out(d) for d in documents]


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentOut)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_permission("manage_knowledge_base")),
):
    """Full source detail view for one document (spec section 6: 'Source
    Details', 'Indexing Status')."""
    document = db.get(KnowledgeDocument, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return _to_out(document)


@router.patch("/documents/{document_id}", response_model=KnowledgeDocumentOut)
def update_document(
    document_id: str,
    data: DocumentUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_permission("manage_knowledge_base")),
):
    """Publish/unpublish (is_active) and metadata correction (spec sections
    6, 27). Unpublishing hides the document from RAG retrieval immediately
    (see knowledge_base_service.retrieve()'s active-document filter) without
    deleting its file or chunks, so it can be republished later."""
    document = db.get(KnowledgeDocument, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    changes = data.model_dump(exclude_unset=True)
    was_active = document.is_active
    for field, value in changes.items():
        setattr(document, field, value)
    db.add(document)
    db.commit()
    db.refresh(document)

    if "is_active" in changes and changes["is_active"] != was_active:
        audit_service.log_event(
            db,
            action="knowledge_base.document.publish" if document.is_active else "knowledge_base.document.unpublish",
            user_id=str(current_admin.id),
            resource_type="knowledge_document",
            resource_id=document_id,
        )
    return _to_out(document)


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_admin=Depends(require_permission("manage_knowledge_base")),
):
    document = db.get(KnowledgeDocument, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    storage_path = document.storage_path
    db.delete(document)
    db.commit()
    if storage_path:
        get_storage_backend().delete(storage_path)
    knowledge_base_service.reembed_all_chunks(db)
    audit_service.log_event(
        db,
        action="knowledge_base.document.delete",
        user_id=str(current_admin.id),
        resource_type="knowledge_document",
        resource_id=document_id,
    )
    return None


@router.post("/query", response_model=RagAnswer, dependencies=[Depends(rate_limit_ai)])
def query_knowledge_base(
    request: Request,
    data: RagQuery,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
):
    result = knowledge_base_service.answer_query(db, data.query, disorder_category=data.disorder_category)
    return result
