"""Tests for the centralized AI Model Registry (spec section 34) and the
optional RAG reranking pass built on top of it."""
from unittest.mock import patch

from tests.conftest import auth_headers


def test_model_registry_requires_manage_models_permission(client, user_token):
    r = client.get("/api/v1/admin/models", headers=auth_headers(user_token))
    assert r.status_code == 403


def test_model_registry_admin_view(client, admin_token):
    r = client.get("/api/v1/admin/models", headers=auth_headers(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert len(body) >= 5
    names = {m["model_name"] for m in body}
    assert "openai/whisper-large-v3-turbo" in names
    assert "BAAI/bge-reranker-v2-m3" in names
    for m in body:
        # Every record must carry the full honest-metadata contract (spec 34).
        for field in ("model_name", "role", "task", "language", "provider", "license", "validated", "limitations"):
            assert field in m


def test_registry_reflects_configured_credentials(client, admin_token, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "HF_API_TOKEN", "")
    r = client.get("/api/v1/admin/models", headers=auth_headers(admin_token))
    hf_models = [m for m in r.json() if m["provider"] == "huggingface_inference_api"]
    assert hf_models and all(m["enabled"] is False for m in hf_models)

    monkeypatch.setattr(settings, "HF_API_TOKEN", "fake-token-for-test")
    r = client.get("/api/v1/admin/models", headers=auth_headers(admin_token))
    hf_models = [m for m in r.json() if m["provider"] == "huggingface_inference_api"]
    assert hf_models and all(m["enabled"] is True for m in hf_models)


# --- reranker: disabled by default, and fails open (never breaks the assistant) ---
def test_reranker_disabled_by_default_keeps_original_order():
    from app.services.knowledge_base_service import _rerank

    results = [{"content": "a", "relevance_score": 0.1}, {"content": "b", "relevance_score": 0.2}]
    assert _rerank("query", results, top_k=5) == results


def test_reranker_falls_back_on_error(monkeypatch):
    from app.core.config import settings
    from app.services.knowledge_base_service import _rerank

    monkeypatch.setattr(settings, "HF_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
    results = [{"content": "a"}, {"content": "b"}, {"content": "c"}]

    with patch("app.services.knowledge_base_service.hf_inference.rerank", side_effect=RuntimeError("network down")):
        assert _rerank("query", results, top_k=5) == results


def test_reranker_reorders_by_score(monkeypatch):
    from app.core.config import settings
    from app.services.knowledge_base_service import _rerank

    monkeypatch.setattr(settings, "HF_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
    results = [{"content": "low"}, {"content": "high"}, {"content": "mid"}]

    with patch("app.services.knowledge_base_service.hf_inference.rerank", return_value=[0.1, 0.9, 0.5]):
        reranked = _rerank("query", results, top_k=2)
    assert [r["content"] for r in reranked] == ["high", "mid"]


def test_reranker_falls_back_on_mismatched_score_count(monkeypatch):
    from app.core.config import settings
    from app.services.knowledge_base_service import _rerank

    monkeypatch.setattr(settings, "HF_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
    results = [{"content": "a"}, {"content": "b"}]

    with patch("app.services.knowledge_base_service.hf_inference.rerank", return_value=[0.5]):
        assert _rerank("query", results, top_k=5) == results
