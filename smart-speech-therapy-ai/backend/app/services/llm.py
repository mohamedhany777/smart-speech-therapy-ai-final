"""
LLM-generated answer synthesis for the RAG pipeline (spec sections 13, 42-43,
57 hallucination control).

Only activates when OPENAI_API_KEY is set (see app/core/config.py). Makes a
real network call to OpenAI's Chat Completions API via the official SDK —
this was not testable live in the sandbox this was built in (its network
allowlist blocks api.openai.com), so verify it end-to-end once a real key is
configured.

Grounding approach: the model is given ONLY the retrieved excerpts as
context and explicitly instructed to answer solely from them, to say so
when they're insufficient, and never to use outside/general knowledge. This
doesn't make hallucination impossible, but it's the standard, documented
mitigation — paired with the fact that every excerpt is already shown to
the user separately with full citations, so a person can always verify the
generated answer against the real source text.
"""
from app.core.config import settings

SYSTEM_PROMPT = (
    "You are a knowledge base assistant for a speech and language therapy "
    "platform. You must answer ONLY using the excerpts provided below — "
    "never use outside knowledge, and never speculate. If the excerpts do "
    "not contain enough information to answer the question, say so "
    "explicitly instead of guessing. Never provide a medical diagnosis; "
    "use screening/informational language only (e.g. 'the material "
    "describes...', not 'you have...'). Keep the answer concise (2-4 "
    "sentences) and speak directly to the question asked."
)


def is_configured() -> bool:
    return bool(settings.OPENAI_API_KEY)


def _format_excerpt(index: int, excerpt: dict) -> str:
    source = excerpt.get("title") or "unknown source"
    page = excerpt.get("page_number")
    page_str = f", p.{page}" if page else ""
    return f"[Excerpt {index + 1}] (Source: {source}{page_str})\n{excerpt['content']}"


def generate_grounded_answer(query: str, excerpts: list[dict]) -> str | None:
    if not is_configured():
        return None

    from openai import OpenAI

    context = "\n\n".join(_format_excerpt(i, ex) for i, ex in enumerate(excerpts))

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=settings.OPENAI_CHAT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Excerpts:\n\n{context}\n\nQuestion: {query}"},
        ],
        temperature=0.2,
        max_tokens=400,
    )
    return response.choices[0].message.content


# --- Disorder-profile extraction (admin content-authoring aid) -------------

DISORDER_EXTRACTION_SYSTEM_PROMPT = (
    "You help a speech-language therapy platform's admin author disorder "
    "reference pages from source documents. You must extract information "
    "ONLY from the provided document text — never add outside knowledge, "
    "never invent facts, and never make diagnostic claims. Write in "
    "descriptive, professional, screening-appropriate language (e.g. "
    "'this disorder is characterized by...', never 'you have...'). If the "
    "document does not clearly describe a single speech/language/"
    "communication disorder, say so honestly in the notes field instead of "
    "forcing an answer.\n\n"
    "Respond with ONLY a JSON object with exactly these keys: "
    '"suggested_name" (the disorder\'s common name, or null), '
    '"suggested_slug" (a URL-friendly slug like "childhood-apraxia-of-speech", or null), '
    '"overview" (2-4 sentences, or null), '
    '"possible_characteristics" (a short paragraph or semicolon-separated list, or null), '
    '"speech_features" (a short paragraph, or null), '
    '"assessment_notes" (a short paragraph on how it is typically assessed, or null), '
    '"extraction_note" (a short string: what you found, or why extraction was limited/uncertain).'
)


def extract_disorder_profile(document_text: str) -> dict:
    """Returns a DRAFT disorder profile extracted from `document_text` for
    an admin to review and edit before saving — never auto-published.
    Returns {"available": False, "note": ...} if no OPENAI_API_KEY is
    configured, consistent with every other optional-AI feature in this
    project (real graceful degradation, not a fabricated draft)."""
    if not is_configured():
        return {
            "available": False,
            "note": (
                "AI-assisted extraction requires OPENAI_API_KEY to be configured. "
                "You can still fill in the disorder profile manually."
            ),
        }

    import json

    from openai import OpenAI

    # Cap input length defensively — extraction only needs the substantive
    # content, not an entire book; keeps cost/latency predictable.
    truncated_text = document_text[:12000]

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=settings.OPENAI_CHAT_MODEL,
        messages=[
            {"role": "system", "content": DISORDER_EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": f"Document text:\n\n{truncated_text}"},
        ],
        temperature=0.1,
        max_tokens=800,
        response_format={"type": "json_object"},
    )

    try:
        parsed = json.loads(response.choices[0].message.content)
    except (json.JSONDecodeError, TypeError) as exc:
        return {"available": False, "note": f"Could not parse the model's response as JSON: {exc}"}

    return {
        "available": True,
        "suggested_name": parsed.get("suggested_name"),
        "suggested_slug": parsed.get("suggested_slug"),
        "overview": parsed.get("overview"),
        "possible_characteristics": parsed.get("possible_characteristics"),
        "speech_features": parsed.get("speech_features"),
        "assessment_notes": parsed.get("assessment_notes"),
        "note": parsed.get("extraction_note")
        or "AI-drafted from the uploaded document — review and edit before saving.",
    }
