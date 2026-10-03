"""
Shared Hugging Face Inference API client.

Architectural rationale: rather than downloading and loading model weights
locally (expensive in RAM — a real problem on a resource-constrained
deployment, e.g. Render's free tier gives only 512MB RAM / 0.1 CPU), this
calls Hugging Face's hosted serverless Inference API — the actual model
computation runs on HF's infrastructure, and our server just makes a
lightweight HTTP request and waits for the result. This is a deliberate
choice for handling load: our tiny instance is never blocked doing heavy
ML inference, only brief I/O-bound waiting, which scales far better under
concurrent requests than loading a model in-process.

Trade-offs, stated honestly:
- Requires a real HF_API_TOKEN and real internet access from the server
  (works on Render/any real host; could not be tested from the sandbox
  this project was built in — see project README).
- Free-tier Inference API has rate limits and can return a 503 with
  "model is loading" for models that aren't warm — handled below with one
  automatic retry after the estimated wait time.
- For very high, sustained traffic, a dedicated Inference Endpoint (paid)
  or self-hosted GPU would be more reliable — this is the right choice for
  a demo or moderate-traffic deployment, not massive scale.
"""
import time

import httpx

from app.core.config import settings

INFERENCE_API_BASE = "https://api-inference.huggingface.co/models"


class HFInferenceError(Exception):
    pass


def is_configured() -> bool:
    return bool(settings.HF_API_TOKEN)


def call_inference_api(model_id: str, data: bytes | dict, content_type: str | None = None, timeout: float = 30.0) -> dict | list:
    """POST to a model's Inference API endpoint. Retries once if the model
    is cold-starting (HF returns 503 + estimated_time while it loads)."""
    if not is_configured():
        raise HFInferenceError("HF_API_TOKEN is not configured")

    headers = {"Authorization": f"Bearer {settings.HF_API_TOKEN}"}
    if content_type:
        headers["Content-Type"] = content_type

    url = f"{INFERENCE_API_BASE}/{model_id}"
    kwargs = {"content": data} if isinstance(data, bytes) else {"json": data}

    response = httpx.post(url, headers=headers, timeout=timeout, **kwargs)

    if response.status_code == 503:
        try:
            wait_time = min(response.json().get("estimated_time", 10), 30)
        except Exception:  # noqa: BLE001
            wait_time = 10
        time.sleep(wait_time)
        response = httpx.post(url, headers=headers, timeout=timeout, **kwargs)

    if response.status_code != 200:
        raise HFInferenceError(f"HF Inference API error ({response.status_code}) for {model_id}: {response.text[:300]}")

    return response.json()


def rerank(model: str, query: str, candidates: list[str]) -> list[float]:
    """Score each candidate's relevance to `query` using a cross-encoder
    reranker (e.g. BAAI/bge-reranker-v2-m3), via the HF Inference API's
    documented sentence-similarity pipeline contract:
        {"inputs": {"source_sentence": query, "sentences": [...]}}
    -> list[float] scores, same order as `candidates`.

    NOTE ON VERIFICATION: this request shape matches HF's published
    sentence-similarity pipeline spec and the target model's
    sentence-transformers tags, but has not been exercised against a live
    HF_API_TOKEN + real network from this project's build environment (see
    README / docs/FINAL_UPGRADE_PLAN.md). Callers (see
    knowledge_base_service._rerank) must treat any failure here as
    non-fatal and fall back to the pre-rerank ordering.
    """
    if not candidates:
        return []
    result = call_inference_api(model, {"inputs": {"source_sentence": query, "sentences": candidates}})
    if not isinstance(result, list) or len(result) != len(candidates):
        raise HFInferenceError(f"Unexpected reranker response shape from {model}: {type(result)}")
    return [float(s) for s in result]
