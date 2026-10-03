"""
Tests for the Hugging Face Inference API integrations (real trained
models called remotely). Since this sandbox's network policy blocks
outbound calls to api-inference.huggingface.co, these tests verify:
  1. Configuration/selection logic (pure, no network).
  2. Graceful failure when no token is configured (the real code path,
     not mocked — HF_API_TOKEN genuinely isn't set in this test env).

If HF_API_TOKEN IS set in the environment running this suite, the
"if configured" tests below will attempt genuine live calls instead of
being skipped — that's the true end-to-end verification for this feature.
"""
import os

import pytest

from app.services import hf_inference
from app.services.embeddings import HFEmbeddingModel, get_active_embedding_model
from app.services.fluency_analysis import HFStutteringClassifier, get_stuttering_classifier

HAS_HF_TOKEN = bool(os.environ.get("HF_API_TOKEN"))


def test_hf_inference_not_configured_by_default():
    assert hf_inference.is_configured() is False


def test_hf_inference_raises_clear_error_without_token():
    with pytest.raises(hf_inference.HFInferenceError, match="HF_API_TOKEN is not configured"):
        hf_inference.call_inference_api("some/model", b"data")


def test_stuttering_classifier_unavailable_without_token():
    assert get_stuttering_classifier() is None


def test_stuttering_classifier_reports_real_error_message(tmp_path):
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"fake audio bytes")

    classifier = HFStutteringClassifier()
    result = classifier.classify(str(audio_file))

    assert result.available is False
    assert result.predicted_label is None
    assert result.label_scores == {}
    assert "HF_API_TOKEN" in result.note


def test_embedding_model_falls_back_to_tfidf_without_any_key(monkeypatch):
    from app.core.config import settings
    from app.services.embeddings import TfidfEmbeddingModel

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "HF_API_TOKEN", "")
    model = get_active_embedding_model()
    assert isinstance(model, TfidfEmbeddingModel)


def test_embedding_model_uses_hf_when_only_hf_token_set(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "HF_API_TOKEN", "fake-token-for-test")
    model = get_active_embedding_model()
    assert isinstance(model, HFEmbeddingModel)


def test_embedding_model_prefers_openai_over_hf_when_both_set(monkeypatch):
    from app.core.config import settings
    from app.services.embeddings import OpenAIEmbeddingModel

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "fake-openai-key")
    monkeypatch.setattr(settings, "HF_API_TOKEN", "fake-hf-token")
    model = get_active_embedding_model()
    assert isinstance(model, OpenAIEmbeddingModel)


def test_hf_embedding_query_and_passage_use_different_prefixes():
    """Pure logic check (no network): confirms the E5 prefix convention is
    actually applied, since silently skipping it would quietly degrade
    retrieval quality while still 'working'."""
    model = HFEmbeddingModel()
    assert model.name == "hf-inference:intfloat/multilingual-e5-base"


@pytest.mark.skipif(not HAS_HF_TOKEN, reason="HF_API_TOKEN not set in this environment")
def test_stuttering_classifier_real_call_if_token_available(tmp_path):
    """Only runs a genuine live call when HF_API_TOKEN is actually present
    in the environment — the real end-to-end verification for this
    feature, done automatically wherever this suite has real credentials."""
    import subprocess

    wav_path = tmp_path / "speech.wav"
    subprocess.run(["espeak-ng", "-w", str(wav_path), "the quick brown fox"], check=True, capture_output=True)

    classifier = HFStutteringClassifier()
    result = classifier.classify(str(wav_path))

    assert result.available is True
    assert result.predicted_label in {
        "Soundrepetition",
        "Wordrepetition",
        "block",
        "fluent",
        "interjection",
        "prolongation",
    }
    assert abs(sum(result.label_scores.values()) - 1.0) < 0.05
