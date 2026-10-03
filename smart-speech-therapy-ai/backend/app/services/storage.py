"""
File storage abstraction (spec sections 63, 65).

Local filesystem storage for development; the interface is deliberately
narrow (`save`, `path_for`, `delete`) so swapping in an S3/MinIO-backed
implementation later doesn't require touching calling code.
"""
import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm"}
ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}

MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB

# Magic-byte signatures per extension (spec section 65 — never trust a
# client-supplied filename/extension alone). Checked in addition to the
# extension, not instead of it: someone could rename "payload.exe" to
# "song.wav" and pass the extension check alone, but its actual bytes won't
# start with "RIFF". .docx is a zip container (starts with "PK"); .txt/.md
# have no reliable binary signature (any byte sequence can be plain text)
# so they are intentionally not magic-byte-checked here — extension +
# size limit is the real control for those two.
_MAGIC_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    ".wav": (b"RIFF",),
    ".mp3": (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"),
    ".flac": (b"fLaC",),
    ".ogg": (b"OggS",),
    ".m4a": (b"\x00\x00\x00", b"ftyp"),  # checked via substring below, not prefix
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".webp": (b"RIFF",),
    ".mp4": (b"ftyp",),  # checked via substring below, not strict prefix
    ".mov": (b"ftyp", b"moov"),
    ".webm": (b"\x1a\x45\xdf\xa3",),
    ".pdf": (b"%PDF-",),
    ".docx": (b"PK\x03\x04",),
}
_SUBSTRING_CHECK_EXTENSIONS = {".m4a", ".mp4", ".mov"}  # container formats: signature isn't always byte 0


class StorageBackend(ABC):
    @abstractmethod
    def save(self, subdir: str, filename: str, content: bytes) -> str:
        """Persist bytes, return a storage_path that `delete`/`path_for` can use."""

    @abstractmethod
    def path_for(self, storage_path: str) -> Path: ...

    @abstractmethod
    def delete(self, storage_path: str) -> None: ...


class LocalStorageBackend(StorageBackend):
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save(self, subdir: str, filename: str, content: bytes) -> str:
        target_dir = self.base_path / subdir
        target_dir.mkdir(parents=True, exist_ok=True)

        # Never trust the uploaded filename directly (spec section 65) —
        # generate a safe, random name and keep only the validated extension.
        ext = Path(filename).suffix.lower()
        safe_name = f"{uuid.uuid4().hex}{ext}"
        full_path = target_dir / safe_name

        with open(full_path, "wb") as f:
            f.write(content)

        return f"{subdir}/{safe_name}"

    def path_for(self, storage_path: str) -> Path:
        return self.base_path / storage_path

    def delete(self, storage_path: str) -> None:
        path = self.path_for(storage_path)
        if path.exists():
            os.remove(path)


def get_storage_backend() -> StorageBackend:
    # STORAGE_BACKEND=s3 would return an S3-backed implementation here in
    # production; only "local" is implemented in this scaffold.
    return LocalStorageBackend(settings.STORAGE_LOCAL_PATH)


def validate_upload(file: UploadFile, allowed_extensions: set[str], content: bytes) -> str:
    """Validate extension + size + (for binary formats with a reliable
    signature) actual file content, not just the client-supplied filename.
    Returns the lowercase extension."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(allowed_extensions)}",
        )
    if len(content) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds max size of {MAX_UPLOAD_BYTES // (1024*1024)}MB",
        )

    signatures = _MAGIC_SIGNATURES.get(ext)
    if signatures:
        header = content[:64]
        if ext in _SUBSTRING_CHECK_EXTENSIONS:
            matched = any(sig in header for sig in signatures)
        else:
            matched = any(header.startswith(sig) for sig in signatures)
        if not matched:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"File content does not match the expected format for '{ext}' "
                    "(the file extension doesn't match its actual content)."
                ),
            )

    return ext
