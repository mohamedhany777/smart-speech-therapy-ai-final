import subprocess

import pytest

from app.services.fluency_analysis import FluencyPatternDetector

HAS_ESPEAK = subprocess.run(["which", "espeak-ng"], capture_output=True).returncode == 0


@pytest.mark.skipif(not HAS_ESPEAK, reason="espeak-ng not installed")
def test_fluency_detector_runs_on_real_speech(tmp_path):
    wav_path = tmp_path / "speech.wav"
    subprocess.run(
        ["espeak-ng", "-w", str(wav_path), "the cat sat on the mat"],
        check=True,
        capture_output=True,
    )

    detector = FluencyPatternDetector()
    result = detector.analyze(str(wav_path))

    assert result.analyzed_frames > 0
    assert result.repetition_candidate_count >= 0
    assert result.prolongation_candidate_count >= 0
    assert result.abrupt_cutoff_count >= 0
    assert "unvalidated" in result.limitations.lower()


@pytest.mark.skipif(not HAS_ESPEAK, reason="espeak-ng not installed")
def test_fluency_detector_shows_higher_indicators_for_repeated_speech(tmp_path):
    """Directional sanity check: repeated-syllable-style speech should show
    at least as many repetition-like patterns as clean, fluent speech."""
    repeated = tmp_path / "repeated.wav"
    clean = tmp_path / "clean.wav"
    subprocess.run(
        ["espeak-ng", "-w", str(repeated), "b-b-b-but I I I want to to to go now", "-s", "120"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["espeak-ng", "-w", str(clean), "but I want to go now", "-s", "120"],
        check=True,
        capture_output=True,
    )

    detector = FluencyPatternDetector()
    repeated_result = detector.analyze(str(repeated))
    clean_result = detector.analyze(str(clean))

    assert repeated_result.repetition_candidate_count >= clean_result.repetition_candidate_count


def test_fluency_detector_handles_very_short_audio_gracefully(tmp_path):
    import wave

    wav_path = tmp_path / "tiny.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 100)  # a few milliseconds

    detector = FluencyPatternDetector()
    result = detector.analyze(str(wav_path))

    assert result.analyzed_frames == 0
    assert "too short" in result.limitations.lower()
