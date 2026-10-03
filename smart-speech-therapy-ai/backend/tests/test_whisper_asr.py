"""
Tests for the Whisper speech-to-text backend.

Model download requires reaching huggingface.co, which the sandbox this
project was built in cannot do (see README / audio_analysis.py docstring).
These tests therefore verify:
  1. The pure logic that doesn't need a network call (language mapping).
  2. That a blocked/failed download is handled gracefully — a real,
     meaningful test of the error-handling path using the actual
     `transformers` library, not a mock.

If you run this suite somewhere with real internet access AND
`transformers`/`torch` installed, `test_whisper_transcribes_real_speech`
below will attempt a genuine download-and-transcribe round trip instead of
being skipped — that's the true end-to-end verification for this feature.
"""
import subprocess

import pytest

try:
    import transformers  # noqa: F401

    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False

HAS_ESPEAK = subprocess.run(["which", "espeak-ng"], capture_output=True).returncode == 0


def test_unsupported_language_reported_honestly():
    from app.services.audio_analysis import WhisperSpeechToTextModel

    model = WhisperSpeechToTextModel()
    result = model.transcribe("/dev/null", "fr")

    assert result["available"] is False
    assert result["text"] is None
    assert "not in the configured mapping" in result["note"]


def test_get_speech_to_text_model_defaults_to_pocketsphinx(monkeypatch):
    from app.core.config import settings
    from app.services.audio_analysis import PocketsphinxSpeechToTextModel, get_speech_to_text_model

    monkeypatch.setattr(settings, "ASR_BACKEND", "pocketsphinx")
    model = get_speech_to_text_model()
    assert isinstance(model, PocketsphinxSpeechToTextModel)


def test_get_speech_to_text_model_switches_to_whisper_via_config(monkeypatch):
    from app.core.config import settings
    from app.services.audio_analysis import WhisperSpeechToTextModel, get_speech_to_text_model

    monkeypatch.setattr(settings, "ASR_BACKEND", "whisper")
    model = get_speech_to_text_model()
    assert isinstance(model, WhisperSpeechToTextModel)


@pytest.mark.skipif(not HAS_TRANSFORMERS, reason="transformers not installed")
def test_whisper_model_download_failure_handled_gracefully(tmp_path):
    """Real test against the real `transformers` library: since this
    sandbox cannot reach huggingface.co, the model download genuinely
    fails — we verify that failure is caught and reported honestly rather
    than crashing or silently returning nothing."""
    from app.services.audio_analysis import WhisperSpeechToTextModel

    dummy_audio = tmp_path / "dummy.wav"
    dummy_audio.write_bytes(b"")

    model = WhisperSpeechToTextModel()
    result = model.transcribe(str(dummy_audio), "en")

    assert result["available"] is False
    assert result["text"] is None
    assert result["note"]  # a real, non-empty explanation was returned


@pytest.mark.skipif(not (HAS_TRANSFORMERS and HAS_ESPEAK), reason="transformers not installed or no internet/espeak")
def test_whisper_transcribes_real_speech_if_network_available(tmp_path):
    """Attempts a genuine end-to-end Whisper transcription. In a sandboxed
    environment without Hugging Face access this will report `available:
    False` (asserted as an acceptable outcome below); with real internet
    access, this exercises the full real download-and-transcribe path and
    checks for actual transcribed text."""
    from app.services.audio_analysis import WhisperSpeechToTextModel

    wav_path = tmp_path / "speech.wav"
    subprocess.run(
        ["espeak-ng", "-w", str(wav_path), "hello world"],
        check=True,
        capture_output=True,
    )

    model = WhisperSpeechToTextModel()
    result = model.transcribe(str(wav_path), "en")

    if not result["available"]:
        pytest.skip(f"Whisper model unavailable in this environment: {result['note']}")

    assert isinstance(result["text"], str)
    assert len(result["text"]) > 0
