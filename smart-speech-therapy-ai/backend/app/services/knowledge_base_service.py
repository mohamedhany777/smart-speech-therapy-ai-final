"""
Knowledge Base ingestion + retrieval (spec sections 10, 11, 13, 16-18, 102).

Ingestion pipeline: text extraction -> cleaning -> chunking -> embedding ->
Qdrant vector store (spec section 54) -> retrieval by real similarity
search. Every citation carries full metadata (title, author, page, section).

Two operating modes, chosen automatically by whether OPENAI_API_KEY is set
(see app/services/embeddings.py and app/services/llm.py):
- Without a key (default): TF-IDF embeddings + extractive response —
  `answer_query()` returns the top retrieved excerpts verbatim rather than
  a generated paragraph, because no LLM is available to synthesize one
  without risking fabrication.
- With a key: real OpenAI embeddings (much better retrieval quality) and a
  real LLM-generated answer, strictly grounded in and citing the retrieved
  excerpts — see app/services/llm.py for the grounding approach.
"""
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.knowledge_base import DocumentChunk, KnowledgeDocument
from app.services import hf_inference, llm, web_search
from app.services.embeddings import get_active_embedding_model, serialize_vector
from app.services.vector_store import get_vector_store

CHUNK_SIZE_CHARS = 1200
CHUNK_OVERLAP_CHARS = 150
MIN_RELEVANCE_SCORE = 0.05  # below this, we say "insufficient evidence" rather than guess


def extract_text(file_path: str, extension: str) -> str:
    """Real text extraction for the formats this scaffold supports.
    PDF layout/OCR handling (spec section 101) is out of scope here —
    scanned/complex PDFs would need an OCR step (e.g. pytesseract) added
    to this function."""
    ext = extension.lower()
    if ext in (".txt", ".md"):
        return Path(file_path).read_text(encoding="utf-8", errors="ignore")
    if ext == ".pdf":
        import pypdf

        reader = pypdf.PdfReader(file_path)
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    if ext == ".docx":
        import docx

        document = docx.Document(file_path)
        return "\n\n".join(p.text for p in document.paragraphs if p.text.strip())
    raise ValueError(f"Text extraction not implemented for extension '{ext}'")


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE_CHARS, overlap: int = CHUNK_OVERLAP_CHARS) -> list[str]:
    """Simple sliding-window chunking on cleaned whitespace. Good enough for
    a real, working baseline; a production system would prefer
    sentence/section-aware chunking."""
    cleaned = " ".join(text.split())
    if not cleaned:
        return []

    chunks = []
    start = 0
    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        chunks.append(cleaned[start:end])
        if end == len(cleaned):
            break
        start = end - overlap
    return chunks


def _chunk_payload(chunk: DocumentChunk, doc: KnowledgeDocument) -> dict:
    return {
        "chunk_id": str(chunk.id),
        "document_id": str(chunk.document_id),
        "content": chunk.content,
        "page_number": chunk.page_number,
        "section": chunk.section,
        "title": doc.title,
        "author": doc.author,
        "publication_year": doc.publication_year,
        "source_type": doc.source_type,
        "source_url": doc.source_url,
    }


def ingest_document_text(db: Session, document: KnowledgeDocument, raw_text: str) -> int:
    """Chunk the given text, store chunks in SQL (the canonical record for
    admin operations / cascading deletes), embed them, and index the
    vectors in Qdrant for real similarity search."""
    pieces = chunk_text(raw_text)
    new_chunks = []
    for i, content in enumerate(pieces):
        chunk = DocumentChunk(document_id=document.id, chunk_index=i, content=content)
        db.add(chunk)
        new_chunks.append(chunk)
    db.commit()
    for chunk in new_chunks:
        db.refresh(chunk)

    model = get_active_embedding_model()
    if model.requires_global_refit:
        # TF-IDF's shared vocabulary means every chunk must be re-embedded
        # together whenever the corpus changes.
        reembed_all_chunks(db)
    else:
        # A hosted dense embedding model can embed just the new chunks and
        # upsert them without touching anything already indexed.
        vectors = model.embed([c.content for c in new_chunks], is_query=False)
        store = get_vector_store()
        points = []
        for chunk, vector in zip(new_chunks, vectors):
            chunk.embedding_model = model.name
            db.add(chunk)
            points.append({"id": str(chunk.id), "vector": vector, "payload": _chunk_payload(chunk, document)})
        store.upsert_chunks(points)
        db.commit()

    return len(pieces)


def reembed_all_chunks(db: Session) -> None:
    """Recompute and re-index every chunk's vector. Required after any
    change when using a global-refit model (TF-IDF); also used to fully
    rebuild the Qdrant index after a document delete."""
    chunks = db.scalars(select(DocumentChunk)).all()
    store = get_vector_store()
    store.clear()
    if not chunks:
        return

    model = get_active_embedding_model()
    corpus = [c.content for c in chunks]
    model.fit(corpus)
    vectors = model.embed(corpus, is_query=False)

    points = []
    for chunk, vector in zip(chunks, vectors):
        chunk.embedding_model = model.name
        db.add(chunk)
        doc = db.get(KnowledgeDocument, chunk.document_id)
        points.append({"id": str(chunk.id), "vector": vector, "payload": _chunk_payload(chunk, doc)})
    db.commit()
    store.upsert_chunks(points)


def _rerank(query: str, results: list[dict], top_k: int) -> list[dict]:
    """Optional cross-encoder reranking pass over the initial embedding-based
    candidates (BAAI/bge-reranker-v2-m3 by default, see model_registry.py).
    Disabled unless HF_RERANKER_MODEL is set - off by default because it adds
    an extra HTTP round-trip per query. NOTE: this call format follows the HF
    Hub's documented sentence-similarity pipeline contract for
    sentence-transformers cross-encoders, but has not been exercised against
    a live token/network from this build environment - treat it as
    untested-in-production until run somewhere with real internet access.
    Falls back to the original embedding-similarity order on any error, so a
    reranker outage never breaks the assistant."""
    if not settings.HF_RERANKER_MODEL or not results:
        return results[:top_k]
    try:
        scores = hf_inference.rerank(
            model=settings.HF_RERANKER_MODEL,
            query=query,
            candidates=[r["content"] for r in results],
        )
        if len(scores) != len(results):
            return results[:top_k]
        reranked = [r for r, _ in sorted(zip(results, scores), key=lambda pair: pair[1], reverse=True)]
        return reranked[:top_k]
    except Exception:  # noqa: BLE001
        return results[:top_k]


def retrieve(db: Session, query: str, top_k: int = 5, disorder_category: str | None = None) -> list[dict]:
    """Real vector search against Qdrant (spec section 13), with optional
    metadata filtering by disorder category. When HF_RERANKER_MODEL is
    configured, over-fetches candidates and reranks them (see `_rerank`).

    Only published (is_active=True) documents are ever searchable here —
    unpublishing a document (spec sections 6, 27: "publish/unpublish
    documents") must take effect immediately, not just hide it from the
    admin document list."""
    fetch_k = top_k * 3 if settings.HF_RERANKER_MODEL else top_k
    model = get_active_embedding_model()
    if model.requires_global_refit:
        # TF-IDF: the query must be embedded in the same vector space as the
        # stored chunks, so re-fit against the current corpus first.
        chunks = db.scalars(select(DocumentChunk)).all()
        if not chunks:
            return []
        model.fit([c.content for c in chunks])
    query_vector = model.embed([query], is_query=True)[0]

    active_ids = {
        str(doc_id) for doc_id in db.scalars(select(KnowledgeDocument.id).where(KnowledgeDocument.is_active.is_(True))).all()
    }
    if not active_ids:
        return []

    document_ids: list[str] | None = list(active_ids)
    if disorder_category:
        category_ids = {
            str(doc_id)
            for doc_id in db.scalars(
                select(KnowledgeDocument.id).where(KnowledgeDocument.disorder_category == disorder_category)
            ).all()
        }
        document_ids = list(active_ids & category_ids)
        if not document_ids:
            return []

    store = get_vector_store()
    hits = store.search(query_vector, top_k=fetch_k, document_ids=document_ids)

    results = []
    for hit in hits:
        if hit["score"] < MIN_RELEVANCE_SCORE:
            continue
        payload = hit["payload"]
        results.append(
            {
                "chunk_id": payload["chunk_id"],
                "content": payload["content"],
                "relevance_score": round(float(hit["score"]), 4),
                "document_id": payload["document_id"],
                "title": payload["title"],
                "author": payload["author"],
                "publication_year": payload["publication_year"],
                "page_number": payload["page_number"],
                "section": payload["section"],
                "source_type": payload["source_type"],
                "source_url": payload["source_url"],
            }
        )
    return _rerank(query, results, top_k)


def answer_query(db: Session, query: str, disorder_category: str | None = None) -> dict:
    """Returns a fully source-traceable response object (spec sections 16-18,
    96-97). The `source_status` field always reflects actual system
    behavior, never a hard-coded claim.

    Knowledge layering (spec section 14): Internal Knowledge Base (Layer 1)
    is tried first. If it has nothing relevant AND TAVILY_API_KEY is set,
    falls back to real web retrieval (Layer 2), filtered/ranked by source
    trust (spec section 15). Without an LLM configured: returns the ranked
    excerpts/web results themselves (extractive), so nothing is ever
    generated/fabricated. With OPENAI_API_KEY set: also includes a real
    LLM-generated answer, strictly instructed to only use the retrieved
    material — see app/services/llm.py.
    """
    results = retrieve(db, query, disorder_category=disorder_category)

    if results:
        generated_answer = llm.generate_grounded_answer(query, results) if llm.is_configured() else None
        return {
            "source_status": "based_on_knowledge_base",
            "message": (
                "Answer generated from Knowledge Base excerpts below."
                if generated_answer
                else "The following knowledge base excerpts are most relevant to your query."
            ),
            "generated_answer": generated_answer,
            "excerpts": results,
            "web_results": [],
        }

    if web_search.is_configured():
        provider = web_search.get_web_search_provider()
        web_results = provider.search(query)
        if web_results:
            web_excerpts = [
                {
                    "chunk_id": None,
                    "content": r["snippet"],
                    "relevance_score": r["trust_score"],
                    "document_id": None,
                    "title": r["title"],
                    "author": None,
                    "publication_year": None,
                    "page_number": None,
                    "section": None,
                    "source_type": "web",
                    "source_url": r["url"],
                }
                for r in web_results
            ]
            generated_answer = llm.generate_grounded_answer(query, web_excerpts) if llm.is_configured() else None
            return {
                "source_status": "based_on_web_sources",
                "message": (
                    "No internal Knowledge Base source was found — the following "
                    "are real, live web search results (not knowledge base "
                    "documents), ranked by source trust."
                ),
                "generated_answer": generated_answer,
                "excerpts": web_excerpts,
                "web_results": web_results,
            }

    return {
        "source_status": "no_source_found",
        "message": (
            "No specific source was retrieved for this query in the "
            "Knowledge Base"
            + (
                ", and web retrieval found no relevant results either."
                if web_search.is_configured()
                else ". No web retrieval is configured in this deployment either"
            )
            + ", so no answer can be generated without fabricating one."
        ),
        "generated_answer": None,
        "excerpts": [],
        "web_results": [],
    }
