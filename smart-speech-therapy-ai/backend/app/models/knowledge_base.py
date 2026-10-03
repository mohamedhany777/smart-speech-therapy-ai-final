"""
RAG Knowledge Base models (spec sections 9-17).

Chunk-level metadata is preserved so every answer can cite a real
document/page/section (spec section 11) — nothing here fabricates a
citation; `DocumentChunk.embedding_json` only exists once real text has
been processed and vectorized by the ingestion pipeline
(app/services/knowledge_base_service.py).
"""
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.types import GUID
from app.models.base import BaseModel


class KnowledgeDocument(BaseModel):
    __tablename__ = "knowledge_documents"

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str] = mapped_column(String(255), nullable=True)
    publication_year: Mapped[int] = mapped_column(Integer, nullable=True)
    edition: Mapped[str] = mapped_column(String(50), nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)

    document_type: Mapped[str] = mapped_column(String(50), nullable=False)  # book | research_paper | guideline | ...
    source_type: Mapped[str] = mapped_column(String(50), default="internal", nullable=False)  # internal | web
    source_url: Mapped[str] = mapped_column(String(1000), nullable=True)

    disorder_category: Mapped[str] = mapped_column(String(255), nullable=True)
    syndrome_category: Mapped[str] = mapped_column(String(255), nullable=True)

    # Ingestion pipeline status (spec section 6): UPLOADED -> PROCESSING ->
    # INDEXED, or FAILED if extraction/embedding failed. ARCHIVED is a
    # terminal admin action distinct from is_active=False ("unpublished" —
    # temporarily hidden from RAG but can be republished; see
    # api/v1/endpoints/knowledge_base.py's publish/unpublish endpoint).
    status: Mapped[str] = mapped_column(String(20), default="UPLOADED", nullable=False, index=True)
    failure_reason: Mapped[str] = mapped_column(Text, nullable=True)

    original_filename: Mapped[str] = mapped_column(String(500), nullable=True)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    uploaded_by_id: Mapped[str] = mapped_column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk", back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(BaseModel):
    __tablename__ = "document_chunks"

    document_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    page_number: Mapped[int] = mapped_column(Integer, nullable=True)
    chapter: Mapped[str] = mapped_column(String(255), nullable=True)
    section: Mapped[str] = mapped_column(String(255), nullable=True)

    # Serialized embedding vector (JSON list of floats) produced by whichever
    # EmbeddingModel implementation is configured — see
    # app/services/embeddings.py for the swappable interface.
    embedding_json: Mapped[str] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=True)

    document: Mapped["KnowledgeDocument"] = relationship("KnowledgeDocument", back_populates="chunks")


class WebSource(BaseModel):
    """A cached trusted-web-source result used as a Layer-2 fallback when the
    internal Knowledge Base doesn't have sufficient coverage (spec section 15).
    Populated by the web retrieval service; never fabricated."""

    __tablename__ = "web_sources"

    query: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=True)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    snippet: Mapped[str] = mapped_column(Text, nullable=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=True)
    retrieved_at: Mapped[str] = mapped_column(String(50), nullable=True)
