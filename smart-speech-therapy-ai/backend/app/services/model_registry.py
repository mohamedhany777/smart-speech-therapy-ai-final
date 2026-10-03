"""
Centralized AI Model Registry.

Every model this platform can call — Hugging Face Inference API models, the
offline PocketSphinx baseline, and the OpenAI chat/embedding fallback — is
declared here in one place with honest, verified metadata: task, language
coverage, provider, license, whether its identity has actually been verified
against the Hugging Face Hub (vs. assumed), and known limitations.

This does NOT ping any external service at request time (the deployment
this was built in has no outbound network access to huggingface.co — see
docs/FINAL_UPGRADE_PLAN.md). "validated" below means the model id, task,
license, and parameter count were confirmed against the live Hugging Face
Hub API on the date noted — a genuine identity/metadata check — not that a
live inference call was benchmarked from this environment. Anything that
would require actually running a model (WER/CER, retrieval quality,
latency under load) is explicitly called out as NOT done here and left for
a deployment with real internet access and a real HF_API_TOKEN.

Do not add a model here "automatically" just because it exists on the Hub —
per spec section 34, only list models this architecture can actually call
(single HTTP POST to the HF serverless Inference API, or a documented local
fallback).
"""
from dataclasses import dataclass, field
from enum import Enum

from app.core.config import settings


class ModelRole(str, Enum):
    ASR = "automatic_speech_recognition"
    EMBEDDING = "text_embedding"
    RERANKER = "reranking"
    AUDIO_CLASSIFICATION = "audio_classification"
    LLM_CHAT = "chat_completion"
    OFFLINE_BASELINE = "offline_baseline"


@dataclass(frozen=True)
class ModelRecord:
    model_name: str
    role: ModelRole
    task: str
    language: str
    provider: str
    version_or_revision: str
    license: str
    validated: bool
    validated_note: str
    limitations: list[str] = field(default_factory=list)
    configurable_via: str | None = None  # settings attribute name, if swappable
    is_current_default: bool = False

    def enabled(self) -> bool:
        """Whether this record's provider is currently reachable given this
        deployment's configuration (a real token/env var present) — not
        whether it has been live-tested."""
        if self.provider == "huggingface_inference_api":
            return bool(settings.HF_API_TOKEN)
        if self.provider == "openai":
            return bool(settings.OPENAI_API_KEY)
        if self.provider == "local":
            return True
        return False


# ---------------------------------------------------------------------------
# Registry — verified against the Hugging Face Hub API on 2026-09-29 via the
# Hugging Face MCP connector (hub_repo_details). See docs/FINAL_UPGRADE_PLAN.md
# section "Model Registry" for the verification transcript/summary.
# ---------------------------------------------------------------------------

REGISTRY: list[ModelRecord] = [
    ModelRecord(
        model_name="openai/whisper-large-v3-turbo",
        role=ModelRole.ASR,
        task="automatic-speech-recognition",
        language="multilingual (99 languages incl. Arabic + English; arabic tag confirmed present)",
        provider="huggingface_inference_api",
        version_or_revision="finetune of openai/whisper-large-v3, 808.9M params",
        license="mit",
        validated=True,
        validated_note=(
            "Confirmed via HF Hub API: task=automatic-speech-recognition, "
            "808.9M params, MIT license, Inference Providers hf-inference "
            "and deepinfra both listed as live at verification time."
        ),
        limitations=[
            "Free-tier serverless Inference API can cold-start (503 + "
            "estimated_time); handled with one retry in hf_inference.py.",
            "No WER/CER has been measured for this deployment's actual "
            "audio conditions — needs a real HF_API_TOKEN + internet "
            "connection to benchmark, which this build environment lacks.",
        ],
        configurable_via="HF_ASR_MODEL",
        is_current_default=True,
    ),
    ModelRecord(
        model_name="itshamdi404/Egy_Arabic_whisper-small",
        role=ModelRole.ASR,
        task="automatic-speech-recognition",
        language="Egyptian Arabic (dialectal)",
        provider="huggingface_inference_api",
        version_or_revision="finetune of openai/whisper-small",
        license="apache-2.0",
        validated=True,
        validated_note=(
            "Confirmed to exist on the Hub: full standalone finetuned "
            "checkpoint (not a LoRA adapter, so it is a drop-in swap via "
            "HF_ASR_MODEL). Only 289 downloads at verification time — "
            "community validation is thin."
        ),
        limitations=[
            "EXPERIMENTAL — not the default. Very low download count means "
            "real-world accuracy is unverified by this project.",
            "Based on whisper-small (39M-244M class), materially less "
            "accurate on non-Egyptian speech than whisper-large-v3-turbo.",
            "No Inference Providers confirmed live for this specific repo "
            "at verification time — may need a paid Inference Endpoint.",
        ],
        configurable_via="HF_ASR_MODEL (opt-in override, not default)",
        is_current_default=False,
    ),
    ModelRecord(
        model_name="intfloat/multilingual-e5-base",
        role=ModelRole.EMBEDDING,
        task="sentence-similarity / feature-extraction",
        language="multilingual (100+ languages incl. Arabic + English)",
        provider="huggingface_inference_api",
        version_or_revision="278.0M params",
        license="mit",
        validated=True,
        validated_note=(
            "Confirmed via HF Hub API: 278M params, MIT license, "
            "Inference Providers: hf-inference (live)."
        ),
        limitations=[
            "Requires 'query: ' / 'passage: ' prefixing convention for best "
            "retrieval quality — see knowledge_base_service.py.",
            "No retrieval-quality benchmark has been run against this "
            "project's actual knowledge base content.",
        ],
        configurable_via="HF_EMBEDDING_MODEL",
        is_current_default=True,
    ),
    ModelRecord(
        model_name="intfloat/multilingual-e5-large",
        role=ModelRole.EMBEDDING,
        task="feature-extraction",
        language="multilingual (100+ languages incl. Arabic + English)",
        provider="huggingface_inference_api",
        version_or_revision="559.9M params",
        license="mit",
        validated=True,
        validated_note="Confirmed via HF Hub API: 559.9M params, MIT license, hf-inference live.",
        limitations=[
            "~2x the params of the default e5-base -> higher latency/cost "
            "per request for (typically) a modest retrieval-quality gain.",
            "Not benchmarked against e5-base on this project's content.",
        ],
        configurable_via="HF_EMBEDDING_MODEL (opt-in upgrade)",
        is_current_default=False,
    ),
    ModelRecord(
        model_name="BAAI/bge-m3",
        role=ModelRole.EMBEDDING,
        task="sentence-similarity",
        language="multilingual (100+ languages incl. Arabic + English)",
        provider="huggingface_inference_api",
        version_or_revision="xlm-roberta base, dense+sparse+multi-vector capable",
        license="mit",
        validated=True,
        validated_note="Confirmed via HF Hub API: MIT license, hf-inference live.",
        limitations=[
            "This project only calls the dense-embedding output through "
            "the plain feature-extraction endpoint — its sparse/ColBERT "
            "multi-vector modes are not usable through the simple HF "
            "serverless Inference API and are NOT implemented here.",
            "Not benchmarked against e5-base on this project's content.",
        ],
        configurable_via="HF_EMBEDDING_MODEL (opt-in alternative)",
        is_current_default=False,
    ),
    ModelRecord(
        model_name="BAAI/bge-reranker-v2-m3",
        role=ModelRole.RERANKER,
        task="text-classification (cross-encoder relevance scoring)",
        language="multilingual (incl. Arabic + English)",
        provider="huggingface_inference_api",
        version_or_revision="567.8M params",
        license="apache-2.0",
        validated=True,
        validated_note="Confirmed via HF Hub API: 567.8M params, apache-2.0, hf-inference live.",
        limitations=[
            "Adds one extra HTTP round-trip per RAG query (reranks the "
            "top-N candidates from the initial embedding search) — "
            "disabled by default to keep the assistant fast; opt-in via "
            "settings.HF_RERANKER_MODEL.",
            "Retrieval-quality improvement not benchmarked in this build "
            "environment (no live internet from the sandboxed backend).",
        ],
        configurable_via="HF_RERANKER_MODEL (opt-in, empty by default)",
        is_current_default=False,
    ),
    ModelRecord(
        model_name="vocametrix/wav2vec2-xlsr-53-stuttering-classification",
        role=ModelRole.AUDIO_CLASSIFICATION,
        task="audio-classification (stuttering / disfluency detection)",
        language="English (trained on SEP-28k / SEP-28k-Extended)",
        provider="huggingface_inference_api",
        version_or_revision="315.7M params, wav2vec2-xlsr-53 based",
        license="apache-2.0",
        validated=True,
        validated_note=(
            "Confirmed via HF Hub API: 315.7M params, apache-2.0, trained "
            "on SEP-28k/SEP-28k-Extended. IMPORTANT: no Inference Providers "
            "were listed as live for this specific repo at verification "
            "time (only 1.9K downloads) — it may 503/404 on the free "
            "serverless tier and require a dedicated (paid) Inference "
            "Endpoint. The audio-feature heuristic fallback in "
            "audio_analysis.py is NOT cosmetic — treat it as the "
            "realistic primary path until this is confirmed live."
        ),
        limitations=[
            "English-only training data — not validated for Arabic speech.",
            "Live availability on the free Inference API is unconfirmed; "
            "code must keep the heuristic fallback as primary, not "
            "best-effort.",
            "The LoRA-adapter alternative pmootr/stuttering-detection-"
            "wavlm-lora is NOT a drop-in replacement (it's an adapter on "
            "microsoft/wavlm-base-plus, not a standalone model callable "
            "via the simple Inference API) and is intentionally not used.",
        ],
        configurable_via="HF_STUTTERING_MODEL",
        is_current_default=True,
    ),
    ModelRecord(
        model_name="gpt-4o-mini",
        role=ModelRole.LLM_CHAT,
        task="chat-completion (assistant answer synthesis, disorder-profile extraction)",
        language="multilingual (incl. Arabic + English)",
        provider="openai",
        version_or_revision="OpenAI-hosted, not on the HF Hub",
        license="proprietary (OpenAI usage terms)",
        validated=False,
        validated_note=(
            "Not verifiable via the Hugging Face Hub (OpenAI-hosted "
            "model). Requires OPENAI_API_KEY + internet access neither of "
            "which is available in this build environment."
        ),
        limitations=[
            "Costs real money per call; only used for synthesis on top of "
            "retrieved KB chunks, never as an unconstrained chat model.",
            "Falls back to a template-based extractive answer (no OpenAI "
            "call) when OPENAI_API_KEY is unset — see llm.py.",
        ],
        configurable_via="OPENAI_CHAT_MODEL",
        is_current_default=True,
    ),
    ModelRecord(
        model_name="pocketsphinx (offline)",
        role=ModelRole.OFFLINE_BASELINE,
        task="automatic-speech-recognition (fully offline baseline)",
        language="English (default acoustic model)",
        provider="local",
        version_or_revision="whatever version pocketsphinx pulls from PyPI",
        license="BSD",
        validated=True,
        validated_note="Runs fully in-process; identity is just the installed package version, not a Hub lookup.",
        limitations=[
            "Materially lower accuracy than Whisper — used only when "
            "HF_API_TOKEN is unset or the HF call fails, so the platform "
            "degrades gracefully instead of hard-failing.",
            "No Arabic support.",
        ],
        configurable_via=None,
        is_current_default=True,
    ),
]


def get_registry() -> list[ModelRecord]:
    return REGISTRY


def get_by_role(role: ModelRole) -> list[ModelRecord]:
    return [m for m in REGISTRY if m.role == role]
