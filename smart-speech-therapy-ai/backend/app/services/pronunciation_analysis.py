"""
Pronunciation analysis (spec section 12).

Pipeline exactly as specified:

    Reference Text -> ASR -> Alignment -> Word Comparison -> Mismatches

This is a deliberately TRANSPARENT, alignment-based implementation, not a
phoneme-level clinical pronunciation model. Real phoneme-level pronunciation
scoring needs a forced-aligner (e.g. Montreal Forced Aligner) or a
purpose-trained pronunciation-assessment model — neither is available in
this build environment, and bolting on a fake phoneme score would violate
the platform's core "never invent a result you can't justify" principle
(spec sections 1, 52). Per spec section 12: "If a strong pretrained
phoneme/pronunciation model is available from Hugging Face, evaluate it
before using it. Otherwise use a transparent alignment-based
implementation." No such model could be evaluated end-to-end from this
build environment (see docs/FINAL_UPGRADE_PLAN.md) — this is the documented
fallback, used honestly as the primary path, not a placeholder.

What this DOES give a real, defensible signal on: whether the words the
recognizer heard match the words the person was asked to say, at the
word level, using nothing invented — a standard sequence-alignment
algorithm (difflib's SequenceMatcher, Python's standard library implementation
of the Ratcliff-Obershelp algorithm) applied to the reference and
recognized word sequences.
"""
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher


def _normalize_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[\w']+", text.lower()) if w]


def estimate_asr_reliability(asr_model_name: str) -> float:
    """Coarse, honestly-documented reliability weight per ASR backend name
    (see audio_analysis.py's SpeechToTextModel.name conventions). Not a
    measured accuracy figure for this deployment (see model_registry.py —
    no WER/CER has been benchmarked from this build environment); this is
    a conservative ranking based on each backend's publicly known relative
    accuracy class (a full neural Whisper model materially outperforms a
    small offline decoder like PocketSphinx on real-world speech)."""
    if asr_model_name.startswith("hf-inference:"):
        return 0.85  # Hosted Whisper-class model via the HF Inference API
    if asr_model_name.startswith("whisper:"):
        return 0.75  # Local Whisper, size/quality varies with WHISPER_MODEL_SIZE
    if asr_model_name == "pocketsphinx":
        return 0.40  # Small offline decoder; materially less accurate
    return 0.30  # Unknown/other backend — conservative default


@dataclass
class WordComparison:
    expected: str | None  # None = an extra word was recognized that wasn't expected (insertion)
    recognized: str | None  # None = an expected word was never recognized (deletion/omission)
    match: bool
    mismatch_type: str  # "match" | "substitution" | "omission" | "insertion"
    confidence: float  # 0-1, see PronunciationResult docstring for what this is (and isn't)

    def to_dict(self) -> dict:
        return {
            "expected": self.expected,
            "recognized": self.recognized,
            "match": self.match,
            "mismatch_type": self.mismatch_type,
            "confidence": self.confidence,
        }


@dataclass
class PronunciationResult:
    available: bool
    note: str
    reference_text: str | None = None
    recognized_text: str | None = None
    accuracy: float | None = None  # matched words / expected words
    word_comparisons: list[WordComparison] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "note": self.note,
            "reference_text": self.reference_text,
            "recognized_text": self.recognized_text,
            "accuracy": self.accuracy,
            "word_comparisons": [w.to_dict() for w in self.word_comparisons],
        }


def analyze_pronunciation(reference_text: str, recognized_text: str, asr_reliability: float) -> PronunciationResult:
    """Compare what the person was asked to say against what the ASR
    recognized, word by word.

    `asr_reliability` (0-1) is a coarse, honestly-labeled per-model
    reliability weight (see audio_analysis.get_speech_to_text_model()) — the
    ASR backends this project uses (PocketSphinx offline, or the HF Whisper
    Inference API) do not return real per-word confidence scores through
    this project's integration, so the "confidence" column the spec asks
    for ("Expected / Recognized / Mismatch / Confidence") is computed as:
    a matched word gets `asr_reliability` (how much to trust the ASR
    backend that produced this transcript in the first place); a mismatched
    word gets a partial-similarity-scaled fraction of that, using the
    same alignment algorithm's per-pair similarity ratio. This is NOT a
    statistical confidence interval or a trained model's probability —
    it is explicitly a heuristic, and is labeled as such wherever it is
    surfaced (see `note` and the frontend's evidence labeling).
    """
    if not reference_text or not reference_text.strip():
        return PronunciationResult(available=False, note="No reference text was provided for this assessment.")
    if not recognized_text or not recognized_text.strip():
        return PronunciationResult(
            available=False,
            note="No speech was recognized in the recording, so it could not be compared to the reference text.",
            reference_text=reference_text,
        )

    expected_words = _normalize_words(reference_text)
    recognized_words = _normalize_words(recognized_text)
    if not expected_words:
        return PronunciationResult(available=False, note="Reference text contained no comparable words.")

    matcher = SequenceMatcher(a=expected_words, b=recognized_words, autojunk=False)
    comparisons: list[WordComparison] = []
    matched_count = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                comparisons.append(
                    WordComparison(
                        expected=expected_words[i],
                        recognized=recognized_words[j],
                        match=True,
                        mismatch_type="match",
                        confidence=round(asr_reliability, 2),
                    )
                )
                matched_count += 1
        elif tag == "replace":
            # Pair up substitutions positionally where lengths allow; any
            # leftover on either side falls through to omission/insertion.
            exp_slice = expected_words[i1:i2]
            rec_slice = recognized_words[j1:j2]
            for k in range(max(len(exp_slice), len(rec_slice))):
                exp_w = exp_slice[k] if k < len(exp_slice) else None
                rec_w = rec_slice[k] if k < len(rec_slice) else None
                if exp_w is None:
                    comparisons.append(
                        WordComparison(None, rec_w, False, "insertion", round(asr_reliability * 0.3, 2))
                    )
                elif rec_w is None:
                    comparisons.append(WordComparison(exp_w, None, False, "omission", 0.0))
                else:
                    similarity = SequenceMatcher(a=exp_w, b=rec_w).ratio()
                    comparisons.append(
                        WordComparison(exp_w, rec_w, False, "substitution", round(asr_reliability * similarity, 2))
                    )
        elif tag == "delete":
            for i in range(i1, i2):
                comparisons.append(WordComparison(expected_words[i], None, False, "omission", 0.0))
        elif tag == "insert":
            for j in range(j1, j2):
                comparisons.append(WordComparison(None, recognized_words[j], False, "insertion", round(asr_reliability * 0.3, 2)))

    accuracy = round(matched_count / len(expected_words), 4)

    return PronunciationResult(
        available=True,
        note=(
            "Word-level alignment between the reference text and the ASR "
            "transcript (Ratcliff-Obershelp sequence matching). This is a "
            "transparent text-comparison screening signal, not a phoneme-"
            "level clinical pronunciation score, and it inherits any "
            "errors made by the underlying speech recognizer."
        ),
        reference_text=reference_text,
        recognized_text=recognized_text,
        accuracy=accuracy,
        word_comparisons=comparisons,
    )
