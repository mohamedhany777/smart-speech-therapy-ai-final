"""
Video analysis pipeline (spec section 29): validate -> extract audio ->
sample frames -> run the real audio pipeline on the extracted audio and the
real image pipeline on sampled frames -> fuse results.

Uses ffmpeg (a real, installed system binary — not a bundled model) for
audio extraction and frame sampling, so this doesn't need any additional
downloaded weights. Frame count is capped (spec section 29: "do not process
unnecessary frames").
"""
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

MAX_SAMPLED_FRAMES = 5


@dataclass
class VideoAnalysisResult:
    duration_seconds: float
    frames_sampled: int
    audio_extracted: bool
    faces_detected_in_frames: int
    note: str

    def to_dict(self) -> dict:
        return asdict(self)


def get_video_duration(file_path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            file_path,
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def extract_audio(video_path: str, output_dir: str) -> str | None:
    """Extract the audio track as a 16kHz mono WAV file, ready for the
    existing audio-analysis pipeline. Returns None if the video has no
    audio track (never fabricates one)."""
    output_path = str(Path(output_dir) / "extracted_audio.wav")
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", "16000", output_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not Path(output_path).exists():
        return None
    return output_path


def sample_frames(video_path: str, output_dir: str, duration: float, max_frames: int = MAX_SAMPLED_FRAMES) -> list[str]:
    """Evenly sample up to `max_frames` frames across the video's duration."""
    if duration <= 0:
        return []

    frame_paths = []
    count = min(max_frames, max(1, int(duration)))
    for i in range(count):
        timestamp = (duration / count) * i + (duration / count) / 2
        frame_path = str(Path(output_dir) / f"frame_{i}.jpg")
        result = subprocess.run(
            ["ffmpeg", "-y", "-ss", str(timestamp), "-i", video_path, "-frames:v", "1", frame_path],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and Path(frame_path).exists():
            frame_paths.append(frame_path)
    return frame_paths


def analyze_video(video_path: str) -> dict:
    """Full fusion pipeline: extract audio + sample frames, run the real
    audio and image analyzers on each, and combine into one structured
    result. Returns raw sub-results so the caller (assessment_service) can
    build the final summary/limitations text using the same honest
    language as the audio/image paths."""
    from app.services.audio_analysis import AudioFeatureExtractor, assess_input_quality
    from app.services.fluency_analysis import FluencyPatternDetector
    from app.services.image_analysis import get_image_analysis_model

    duration = get_video_duration(video_path)

    with tempfile.TemporaryDirectory() as tmp_dir:
        audio_path = extract_audio(video_path, tmp_dir)
        frame_paths = sample_frames(video_path, tmp_dir, duration)

        audio_result = None
        fluency_result = None
        if audio_path:
            extractor = AudioFeatureExtractor()
            audio_features = extractor.extract(audio_path)
            quality_score, quality_issues = assess_input_quality(audio_features)
            fluency = FluencyPatternDetector().analyze(audio_path)
            audio_result = {
                "features": audio_features.to_dict(),
                "quality_score": quality_score,
                "quality_issues": quality_issues,
            }
            fluency_result = fluency.to_dict()

        image_model = get_image_analysis_model()
        frame_results = [image_model.analyze(fp).to_dict() for fp in frame_paths]

    faces_detected = sum(1 for r in frame_results if r["face_detected"])

    video_summary = VideoAnalysisResult(
        duration_seconds=round(duration, 2),
        frames_sampled=len(frame_paths),
        audio_extracted=audio_path is not None,
        faces_detected_in_frames=faces_detected,
        note=(
            "Multimodal fusion: real audio feature extraction on the "
            "extracted audio track, real per-frame image analysis on "
            f"{len(frame_paths)} evenly-sampled frame(s). No video-specific "
            "trained model (e.g. lip-reading, gesture recognition) is used — "
            "results are the same audio/image techniques applied to video-"
            "derived inputs."
        ),
    )

    return {
        "video_summary": video_summary.to_dict(),
        "audio_result": audio_result,
        "fluency_result": fluency_result,
        "frame_results": frame_results,
        "image_model_name": image_model.name,
    }
