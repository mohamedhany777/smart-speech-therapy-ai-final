import subprocess

import numpy as np
import pytest

from app.services.image_analysis import OpenCVFaceAnalyzer

HAS_FFMPEG = subprocess.run(["which", "ffmpeg"], capture_output=True).returncode == 0


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
def test_no_face_detected_on_non_face_image(tmp_path):
    img_path = tmp_path / "pattern.jpg"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:duration=1:rate=1", "-frames:v", "1", str(img_path)],
        check=True,
        capture_output=True,
    )

    analyzer = OpenCVFaceAnalyzer()
    result = analyzer.analyze(str(img_path))

    assert result.available is True
    assert result.face_detected is False
    assert result.face_count == 0
    assert result.resolution == (320, 240)
    assert "No face detected" in result.note
    # Never diagnoses anything from the image.
    assert "diagnos" not in result.note.lower() or "never used to infer a diagnosis" in result.note


def test_analyze_handles_unreadable_file_gracefully(tmp_path):
    bad_file = tmp_path / "not_an_image.jpg"
    bad_file.write_bytes(b"this is not image data")

    analyzer = OpenCVFaceAnalyzer()
    result = analyzer.analyze(str(bad_file))

    assert result.available is False
    assert result.face_detected is False


def test_symmetry_score_discriminates_symmetric_vs_asymmetric():
    left_half = np.random.randint(0, 255, (100, 50), dtype=np.uint8)
    symmetric = np.hstack([left_half, np.fliplr(left_half)])
    score_symmetric = OpenCVFaceAnalyzer._symmetry_score(symmetric)
    assert score_symmetric == 1.0

    asymmetric = np.random.randint(0, 255, (100, 100), dtype=np.uint8)
    score_asymmetric = OpenCVFaceAnalyzer._symmetry_score(asymmetric)
    assert 0.0 <= score_asymmetric < 1.0
    assert score_asymmetric < score_symmetric
