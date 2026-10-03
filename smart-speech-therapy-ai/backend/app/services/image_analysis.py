"""
Image analysis (spec section 28).

Two real implementations, same pattern as the rest of this project (a
local, always-available baseline; an optional cloud upgrade):

- `OpenCVFaceAnalyzer` (default, always available): classical Haar-cascade
  face/eye/smile detection, bundled inside opencv-python — no model
  download needed. This is a ~20-year-old technique, much coarser than a
  modern face-landmark model: it gives face presence, a rough bounding
  box, a crude left/right symmetry score, and eye/smile-region detection
  flags — NOT the fine-grained mouth/lip landmark tracking the original
  spec describes. A stronger option (MediaPipe's face landmarker) needs a
  model-bundle download this sandbox's network allowlist blocks; that
  remains a real upgrade path, just not buildable here.
- `OpenAIVisionAnalyzer` (used automatically when OPENAI_API_KEY is set):
  sends the image to a real vision-capable OpenAI model with a prompt
  that's explicitly restricted to descriptive, non-diagnostic observations
  (spec section 28: never diagnose a communication disorder from
  appearance alone). This makes a genuine network call that could not be
  tested live in the sandbox this was built in.

Per spec section 28, neither implementation ever infers a syndrome,
disorder, or diagnosis from an image — only descriptive/geometric
observations.
"""
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass

import cv2
import numpy as np

_face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
_eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")
_smile_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_smile.xml")


@dataclass
class ImageAnalysisResult:
    available: bool
    model: str
    face_detected: bool
    face_count: int
    eyes_detected: int
    smile_region_detected: bool
    symmetry_score: float | None  # 0-1, rough bounding-box mirror similarity
    brightness_mean: float
    resolution: tuple[int, int]
    note: str
    description: str | None = None  # only populated by a vision-LLM implementation

    def to_dict(self) -> dict:
        d = asdict(self)
        d["resolution"] = list(d["resolution"])
        return d


class ImageAnalysisModel(ABC):
    name: str

    @abstractmethod
    def analyze(self, file_path: str) -> ImageAnalysisResult: ...


class OpenCVFaceAnalyzer(ImageAnalysisModel):
    name = "opencv-haar-cascade"

    def analyze(self, file_path: str) -> ImageAnalysisResult:
        img = cv2.imread(file_path)
        if img is None:
            return ImageAnalysisResult(
                available=False,
                model=self.name,
                face_detected=False,
                face_count=0,
                eyes_detected=0,
                smile_region_detected=False,
                symmetry_score=None,
                brightness_mean=0.0,
                resolution=(0, 0),
                note="Could not read image file (unsupported format or corrupted file).",
            )

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        height, width = gray.shape
        brightness = float(np.mean(gray))

        faces = _face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))

        eyes_detected = 0
        smile_detected = False
        symmetry_score = None

        if len(faces) > 0:
            # Use the largest detected face for sub-region analysis.
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            face_roi = gray[y : y + h, x : x + w]

            eyes = _eye_cascade.detectMultiScale(face_roi, scaleFactor=1.1, minNeighbors=8, minSize=(15, 15))
            eyes_detected = len(eyes)

            smiles = _smile_cascade.detectMultiScale(face_roi, scaleFactor=1.7, minNeighbors=20, minSize=(25, 25))
            smile_detected = len(smiles) > 0

            symmetry_score = self._symmetry_score(face_roi)

        note = (
            "Classical Haar-cascade detection — coarse geometric indicators only "
            "(face presence, rough symmetry, eye/smile-region presence). Not "
            "fine-grained landmark tracking, and never used to infer a diagnosis."
        )
        if len(faces) == 0:
            note = "No face detected in this image. " + note

        return ImageAnalysisResult(
            available=True,
            model=self.name,
            face_detected=len(faces) > 0,
            face_count=len(faces),
            eyes_detected=eyes_detected,
            smile_region_detected=smile_detected,
            symmetry_score=symmetry_score,
            brightness_mean=round(brightness, 2),
            resolution=(width, height),
            note=note,
        )

    @staticmethod
    def _symmetry_score(face_gray: np.ndarray) -> float:
        """Crude left/right mirror-similarity of the face bounding box, as a
        rough facial-symmetry indicator (spec section 28). This compares
        pixel intensities, not actual anatomical landmarks — a real
        clinical symmetry assessment needs landmark-level analysis."""
        h, w = face_gray.shape
        mid = w // 2
        left = face_gray[:, :mid]
        right = face_gray[:, w - mid :]
        right_mirrored = np.fliplr(right)

        # Resize defensively in case of odd-width rounding.
        min_w = min(left.shape[1], right_mirrored.shape[1])
        left = left[:, :min_w].astype(np.float32)
        right_mirrored = right_mirrored[:, :min_w].astype(np.float32)

        diff = np.abs(left - right_mirrored)
        similarity = 1.0 - (float(np.mean(diff)) / 255.0)
        return round(max(0.0, min(1.0, similarity)), 4)


class OpenAIVisionAnalyzer(ImageAnalysisModel):
    """Real OpenAI vision-model analysis. Requires OPENAI_API_KEY. Makes an
    actual network call — not testable live in the sandbox this was built
    in (network allowlist blocks api.openai.com)."""

    name = "openai-vision"

    _PROMPT = (
        "Describe only what is directly, visually observable about this image "
        "in the context of a speech/communication therapy exercise: general "
        "face/mouth position, apparent expression, image quality/lighting. Do "
        "NOT infer, diagnose, or speculate about any medical, developmental, "
        "or communication condition — descriptive observations only, 2-3 "
        "sentences."
    )

    def analyze(self, file_path: str) -> ImageAnalysisResult:
        import base64

        from app.core.config import settings

        baseline = OpenCVFaceAnalyzer().analyze(file_path)

        from openai import OpenAI

        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        with open(file_path, "rb") as f:
            b64_image = base64.b64encode(f.read()).decode("utf-8")

        response = client.chat.completions.create(
            model=settings.OPENAI_CHAT_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}},
                    ],
                }
            ],
            max_tokens=200,
        )

        baseline.model = self.name
        baseline.description = response.choices[0].message.content
        baseline.note = (
            "Descriptive-only observation from a vision-capable LLM, combined "
            "with the OpenCV geometric baseline. Never a diagnosis."
        )
        return baseline


def get_image_analysis_model() -> ImageAnalysisModel:
    from app.core.config import settings

    if settings.OPENAI_API_KEY:
        return OpenAIVisionAnalyzer()
    return OpenCVFaceAnalyzer()
