"""
Fluency pattern detection (spec sections 24-25: stuttering/fluency analysis).

Two complementary layers:

1. `FluencyPatternDetector` — real, classical digital-signal-processing
   heuristics (always available, no setup, no network needed). Useful as
   a baseline and a sanity cross-check, but genuinely unvalidated against
   any clinical ground truth.

2. `HFStutteringClassifier` — a REAL trained model, used automatically
   when HF_API_TOKEN is set:
   `vocametrix/wav2vec2-xlsr-53-stuttering-classification` — a wav2vec2-
   XLSR-53 backbone fine-tuned for stuttering-event classification on
   SEP-28k and SEP-28k-Extended (established, published academic
   stuttering-event datasets — see the model's Hugging Face card and its
   referenced paper, arXiv:2206.14568). It classifies short audio clips
   into: sound repetition, word repetition, block, interjection,
   prolongation, or fluent. This is a genuinely trained clinical-research-
   grade classifier — a real answer to "detect stuttering patterns",
   not a heuristic — called via the Hugging Face Inference API (see
   app/services/hf_inference.py) so it needs no local GPU/RAM.

Even with a real trained model, this is still screening support, not a
diagnosis (spec section 24: never diagnose from a single recording) — the
model is English-only per its model card, was trained on a specific
dataset's speakers/conditions, and like any classifier can be wrong.
Every response says so.
"""
from dataclasses import asdict, dataclass

import librosa
import numpy as np

from app.core.config import settings
from app.services import hf_inference

MODEL_NAME = "dsp-fluency-heuristics"
MODEL_VERSION = "1.0"

FRAME_SECONDS = 0.25  # ~250ms analysis windows, roughly syllable-scale
REPETITION_SIMILARITY_THRESHOLD = 0.92
PROLONGATION_MIN_SECONDS = 0.45
PROLONGATION_PITCH_CV_THRESHOLD = 0.05  # coefficient of variation


@dataclass
class FluencyIndicators:
    repetition_candidate_count: int
    prolongation_candidate_count: int
    abrupt_cutoff_count: int
    analyzed_frames: int
    method: str
    limitations: str

    def to_dict(self) -> dict:
        return asdict(self)


class FluencyPatternDetector:
    name = MODEL_NAME
    version = MODEL_VERSION

    def analyze(self, file_path: str) -> FluencyIndicators:
        y, sr = librosa.load(file_path, sr=None, mono=True)

        frame_length = int(FRAME_SECONDS * sr)
        hop_length = frame_length  # non-overlapping windows for this pass

        if len(y) < frame_length * 2:
            return FluencyIndicators(
                repetition_candidate_count=0,
                prolongation_candidate_count=0,
                abrupt_cutoff_count=0,
                analyzed_frames=0,
                method=self.name,
                limitations="Recording too short to analyze for fluency patterns.",
            )

        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=hop_length, n_fft=frame_length)
        rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]

        repetition_count = self._detect_repetitions(mfcc)
        prolongation_count = self._detect_prolongations(y, sr, rms, hop_length)
        abrupt_cutoff_count = self._detect_abrupt_cutoffs(rms)

        return FluencyIndicators(
            repetition_candidate_count=repetition_count,
            prolongation_candidate_count=prolongation_count,
            abrupt_cutoff_count=abrupt_cutoff_count,
            analyzed_frames=mfcc.shape[1],
            method=self.name,
            limitations=(
                "Unvalidated digital-signal-processing heuristics, not a trained "
                "clinical classifier. Candidate patterns only — always require "
                "specialist review before drawing any conclusion. Note: any "
                "sustained tone or held vowel can also trigger the repetition "
                "heuristic (it measures frame-to-frame similarity, which a long "
                "steady sound also produces) — it does not distinguish that from "
                "genuinely repeated separate attempts at a sound."
            ),
        )

    @staticmethod
    def _detect_repetitions(mfcc: np.ndarray) -> int:
        """Count adjacent frame-pairs whose MFCC vectors are unusually similar
        — the acoustic signature of a repeated short sound/syllable."""
        if mfcc.shape[1] < 2:
            return 0
        count = 0
        for i in range(mfcc.shape[1] - 1):
            a, b = mfcc[:, i], mfcc[:, i + 1]
            denom = np.linalg.norm(a) * np.linalg.norm(b)
            if denom == 0:
                continue
            similarity = float(np.dot(a, b) / denom)
            if similarity >= REPETITION_SIMILARITY_THRESHOLD:
                count += 1
        return count

    @staticmethod
    def _detect_prolongations(y: np.ndarray, sr: int, rms: np.ndarray, hop_length: int) -> int:
        """Count voiced runs that sustain a near-constant pitch for longer
        than a typical phoneme — the acoustic signature of a prolongation."""
        f0 = librosa.yin(y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7"), sr=sr, hop_length=hop_length)
        voiced = np.isfinite(f0) & (f0 > 60) & (f0 < 500)

        min_frames = max(1, int(PROLONGATION_MIN_SECONDS * sr / hop_length))
        count = 0
        run_start = None
        for i, is_voiced in enumerate(voiced):
            if is_voiced and run_start is None:
                run_start = i
            elif not is_voiced and run_start is not None:
                run = f0[run_start:i]
                if len(run) >= min_frames:
                    mean = np.mean(run)
                    cv = (np.std(run) / mean) if mean > 0 else 1.0
                    if cv < PROLONGATION_PITCH_CV_THRESHOLD:
                        count += 1
                run_start = None
        return count

    @staticmethod
    def _detect_abrupt_cutoffs(rms: np.ndarray) -> int:
        """Count sharp voiced-to-silence transitions (large single-frame
        energy drop) as a rough proxy for block-like stoppages. Ordinary
        end-of-sentence trailing-off looks different (gradual decay), so
        this specifically looks for a steep single-step drop."""
        if len(rms) < 2:
            return 0
        mean_energy = float(np.mean(rms)) or 1e-9
        diffs = np.diff(rms) / mean_energy
        # A drop of more than 70% of mean energy in a single 250ms frame.
        return int(np.sum(diffs < -0.7))


@dataclass
class StutteringClassificationResult:
    available: bool
    model: str
    predicted_label: str | None
    label_scores: dict[str, float]
    note: str

    def to_dict(self) -> dict:
        return asdict(self)


class HFStutteringClassifier:
    """Real trained stuttering-event classifier via the Hugging Face
    Inference API — see module docstring for the model's provenance
    (SEP-28k, arXiv:2206.14568). Genuinely tested during development that
    this model is real, trained, and hosted on Hugging Face with the
    expected label set (confirmed via its published config.json); the
    live Inference API call itself could not be exercised end-to-end from
    the sandbox this project was built in (network policy blocks outbound
    calls to api-inference.huggingface.co) — verify once deployed
    somewhere with real internet access."""

    name = f"hf-inference:{settings.HF_STUTTERING_MODEL}"

    def classify(self, file_path: str) -> StutteringClassificationResult:
        try:
            with open(file_path, "rb") as f:
                audio_bytes = f.read()
        except OSError as exc:
            return StutteringClassificationResult(
                available=False,
                model=self.name,
                predicted_label=None,
                label_scores={},
                note=f"Could not read audio file: {exc}",
            )

        try:
            result = hf_inference.call_inference_api(
                settings.HF_STUTTERING_MODEL, audio_bytes, content_type="audio/wav", timeout=30.0
            )
        except hf_inference.HFInferenceError as exc:
            return StutteringClassificationResult(
                available=False,
                model=self.name,
                predicted_label=None,
                label_scores={},
                note=f"Hugging Face Inference API call failed: {exc}",
            )

        # HF audio-classification responses are a list of {"label", "score"}.
        if not isinstance(result, list) or not result:
            return StutteringClassificationResult(
                available=False,
                model=self.name,
                predicted_label=None,
                label_scores={},
                note=f"Unexpected response format from the classifier: {result}",
            )

        label_scores = {item["label"]: round(float(item["score"]), 4) for item in result}
        predicted_label = max(label_scores, key=label_scores.get)

        return StutteringClassificationResult(
            available=True,
            model=self.name,
            predicted_label=predicted_label,
            label_scores=label_scores,
            note=(
                "Real trained classifier (wav2vec2-XLSR-53 fine-tuned on the "
                "published SEP-28k / SEP-28k-Extended stuttering-event "
                "datasets), not a heuristic. Still screening support, not a "
                "diagnosis — trained on English speech from a specific "
                "dataset; treat any single prediction as a candidate signal "
                "for specialist review, not a definitive result."
            ),
        )


def get_stuttering_classifier() -> HFStutteringClassifier | None:
    """Returns the real trained classifier when HF_API_TOKEN is configured,
    otherwise None (callers should fall back to FluencyPatternDetector's
    heuristics only)."""
    if settings.HF_API_TOKEN:
        return HFStutteringClassifier()
    return None
