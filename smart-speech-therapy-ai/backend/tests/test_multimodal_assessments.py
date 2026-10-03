import io
import subprocess

import pytest

from tests.conftest import auth_headers, wait_for_assessment

HAS_FFMPEG = subprocess.run(["which", "ffmpeg"], capture_output=True).returncode == 0


def _make_test_image_bytes() -> bytes:
    result = subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:duration=1:rate=1", "-frames:v", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
        capture_output=True,
    )
    return result.stdout


def _make_test_video_bytes(duration: int = 3) -> bytes:
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"testsrc=size=320x240:duration={duration}:rate=5",
            "-f", "lavfi", "-i", f"sine=frequency=200:duration={duration}",
            "-c:v", "libx264", "-c:a", "aac", "-shortest",
            "-f", "mp4", "-movflags", "frag_keyframe+empty_moov",
            "-",
        ],
        capture_output=True,
    )
    return result.stdout


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
def test_full_image_assessment_flow(client, user_token, specialist_token):
    image_bytes = _make_test_image_bytes()
    assert len(image_bytes) > 0

    upload_resp = client.post(
        "/api/v1/assessments/media/image",
        files={"file": ("test.jpg", io.BytesIO(image_bytes), "image/jpeg")},
        headers=auth_headers(user_token),
    )
    assert upload_resp.status_code == 201
    media = upload_resp.json()
    assert media["media_type"] == "image"

    create_resp = client.post(
        "/api/v1/assessments",
        json={"media_file_id": media["id"], "assessment_type": "image"},
        headers=auth_headers(user_token),
    )
    assert create_resp.status_code == 201
    assessment = wait_for_assessment(client, user_token, create_resp.json()["id"])
    assert assessment["status"] == "completed"

    result = assessment["analysis_result"]
    assert result is not None
    assert result["model_name"] == "opencv-haar-cascade"
    assert "diagnos" not in result["summary"].lower() or "does not diagnose" in result["summary"].lower()
    assert "never infers" in result["limitations"].lower() or "never used to infer" in result["limitations"].lower()


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
def test_full_video_assessment_flow(client, user_token):
    video_bytes = _make_test_video_bytes(duration=3)
    assert len(video_bytes) > 0

    upload_resp = client.post(
        "/api/v1/assessments/media/video",
        files={"file": ("test.mp4", io.BytesIO(video_bytes), "video/mp4")},
        headers=auth_headers(user_token),
    )
    assert upload_resp.status_code == 201
    media = upload_resp.json()
    assert media["media_type"] == "video"

    create_resp = client.post(
        "/api/v1/assessments",
        json={"media_file_id": media["id"], "assessment_type": "video"},
        headers=auth_headers(user_token),
    )
    assert create_resp.status_code == 201
    assessment = wait_for_assessment(client, user_token, create_resp.json()["id"], timeout=30)
    assert assessment["status"] == "completed"

    result = assessment["analysis_result"]
    assert result is not None
    assert result["model_name"] == "video-fusion-pipeline"

    import json as jsonlib

    features = jsonlib.loads(result["features_json"])
    assert features["video_summary"]["audio_extracted"] is True
    assert features["video_summary"]["frames_sampled"] > 0
    # Real signal processing should recover the actual 200Hz tone.
    assert 195 <= features["audio_result"]["features"]["pitch_mean_hz"] <= 205


def test_assessment_type_must_match_media_type(client, user_token):
    import io as io_module

    from tests.audio_fixture import make_wav_bytes

    wav_bytes = make_wav_bytes(duration_seconds=1.0)
    upload_resp = client.post(
        "/api/v1/assessments/media/audio",
        files={"file": ("sample.wav", io_module.BytesIO(wav_bytes), "audio/wav")},
        headers=auth_headers(user_token),
    )
    media_id = upload_resp.json()["id"]

    resp = client.post(
        "/api/v1/assessments",
        json={"media_file_id": media_id, "assessment_type": "image"},
        headers=auth_headers(user_token),
    )
    assert resp.status_code == 400
