import os
import subprocess
import wave

import pytest

from app.services.audio_analysis import PocketsphinxSpeechToTextModel

HAS_ESPEAK = subprocess.run(["which", "espeak-ng"], capture_output=True).returncode == 0


@pytest.mark.skipif(not HAS_ESPEAK, reason="espeak-ng not installed — can't synthesize test speech")
def test_pocketsphinx_transcribes_real_synthesized_speech(tmp_path):
    """Runs a genuine end-to-end ASR decode: synthesize real speech audio
    with espeak-ng, then transcribe it with the actual PocketSphinx engine.
    Not mocked at any layer."""
    wav_path = tmp_path / "speech.wav"
    subprocess.run(
        ["espeak-ng", "-w", str(wav_path), "hello world"],
        check=True,
        capture_output=True,
    )
    assert wav_path.exists() and wav_path.stat().st_size > 0

    model = PocketsphinxSpeechToTextModel()
    result = model.transcribe(str(wav_path), "en")

    assert result["available"] is True
    assert result["language"] == "en"
    # PocketSphinx is low-accuracy; we assert it produced *some* real,
    # non-empty transcript rather than asserting an exact match.
    assert isinstance(result["text"], str)
    assert len(result["text"]) > 0
    assert "rough approximation" in result["note"] or "offline ASR" in result["note"]


def test_pocketsphinx_reports_unavailable_for_non_english(tmp_path):
    wav_path = tmp_path / "silence.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000)

    model = PocketsphinxSpeechToTextModel()
    result = model.transcribe(str(wav_path), "ar")

    assert result["available"] is False
    assert result["text"] is None
    assert "does not support" in result["note"]


def test_pocketsphinx_handles_silence_gracefully(tmp_path):
    wav_path = tmp_path / "silence.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000)

    model = PocketsphinxSpeechToTextModel()
    result = model.transcribe(str(wav_path), "en")

    # Silence should not crash and should not fabricate a transcript.
    assert result["available"] is True
    assert result["text"] is None or result["text"] == ""
