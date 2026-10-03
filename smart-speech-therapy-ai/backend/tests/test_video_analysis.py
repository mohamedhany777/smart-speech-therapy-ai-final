import subprocess

import pytest

from app.services.video_analysis import analyze_video, extract_audio, get_video_duration, sample_frames

HAS_FFMPEG = subprocess.run(["which", "ffmpeg"], capture_output=True).returncode == 0


def _make_test_video(path: str, duration: int = 3) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size=320x240:duration={duration}:rate=5",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=200:duration={duration}",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            path,
        ],
        check=True,
        capture_output=True,
    )


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
def test_get_video_duration_real_file(tmp_path):
    video_path = str(tmp_path / "test.mp4")
    _make_test_video(video_path, duration=3)

    duration = get_video_duration(video_path)
    assert 2.5 < duration < 3.5


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
def test_extract_audio_produces_real_wav(tmp_path):
    video_path = str(tmp_path / "test.mp4")
    _make_test_video(video_path, duration=2)

    audio_path = extract_audio(video_path, str(tmp_path))
    assert audio_path is not None

    import librosa

    y, sr = librosa.load(audio_path, sr=None)
    assert sr == 16000
    assert len(y) > 0


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
def test_sample_frames_produces_real_images(tmp_path):
    video_path = str(tmp_path / "test.mp4")
    _make_test_video(video_path, duration=3)

    frames = sample_frames(video_path, str(tmp_path), duration=3, max_frames=3)
    assert len(frames) == 3
    for frame_path in frames:
        import cv2

        img = cv2.imread(frame_path)
        assert img is not None
        assert img.shape[0] > 0 and img.shape[1] > 0


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
def test_full_video_analysis_pipeline_end_to_end(tmp_path):
    video_path = str(tmp_path / "test.mp4")
    _make_test_video(video_path, duration=3)

    result = analyze_video(video_path)

    assert result["video_summary"]["audio_extracted"] is True
    assert result["video_summary"]["frames_sampled"] == 3
    # Real signal processing should recover the actual 200Hz tone we generated.
    assert result["audio_result"] is not None
    assert 195 <= result["audio_result"]["features"]["pitch_mean_hz"] <= 205
    assert result["fluency_result"] is not None
    assert len(result["frame_results"]) == 3
