import uuid

from pydantic import BaseModel


class KnowledgeDocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    author: str | None
    publication_year: int | None
    document_type: str
    source_type: str
    source_url: str | None = None
    disorder_category: str | None
    language: str
    status: str
    failure_reason: str | None = None
    is_active: bool
    uploaded_by_id: uuid.UUID | None = None
    # Computed from the live relationship at response-build time, never
    # stored, so it can never drift from reality (spec section 6: "see
    # chunk count"). Populated explicitly in the endpoint — see
    # api/v1/endpoints/knowledge_base.py's _to_out().
    chunk_count: int = 0
    model_config = {"from_attributes": True}


class DocumentUploadMeta(BaseModel):
    title: str
    author: str | None = None
    publication_year: int | None = None
    document_type: str = "book"
    disorder_category: str | None = None
    syndrome_category: str | None = None
    language: str = "en"


class DocumentUpdate(BaseModel):
    """Partial update for admin document management (spec sections 6, 27):
    publish/unpublish (is_active) and correcting metadata without needing to
    delete and re-upload the whole document."""

    title: str | None = None
    author: str | None = None
    publication_year: int | None = None
    disorder_category: str | None = None
    is_active: bool | None = None  # False = "unpublish": hidden from RAG, not deleted


class RagQuery(BaseModel):
    query: str
    disorder_category: str | None = None


class RagExcerpt(BaseModel):
    chunk_id: str | None
    content: str
    relevance_score: float
    document_id: str | None
    title: str | None
    author: str | None
    publication_year: int | None
    page_number: int | None
    section: str | None
    source_type: str | None
    source_url: str | None


class RagAnswer(BaseModel):
    source_status: str
    message: str
    generated_answer: str | None = None
    excerpts: list[RagExcerpt]
    web_results: list[dict] = []
