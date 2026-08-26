import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import UploadFile

from app.config import Settings

CONTENT_TYPE_SUFFIXES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
}

MediaPreparationFailureKind = Literal["invalid_input", "unsupported_media", "too_large"]


class MediaPreparationError(ValueError):
    """An upload does not satisfy the configured media contract."""

    def __init__(self, error_code: str, kind: MediaPreparationFailureKind) -> None:
        super().__init__(error_code)
        self.error_code = error_code
        self.kind = kind


@dataclass(frozen=True)
class PreparedMedia:
    """One validated upload saved in a request-scoped temporary directory."""

    path: Path
    content_type: str
    media_kind: str
    sha256: str


def classify_media(content_type: str, settings: Settings) -> tuple[str, str]:
    """Return the canonical media kind and suffix for a supported MIME type."""
    normalized = content_type.lower()
    if normalized in settings.allowed_photo_content_types:
        return "photo", CONTENT_TYPE_SUFFIXES[normalized]
    if normalized in settings.allowed_video_content_types:
        return "video", CONTENT_TYPE_SUFFIXES[normalized]
    raise MediaPreparationError("MEDIA_TYPE_UNSUPPORTED", "unsupported_media")


class UploadedMediaPreparer:
    """Validate uploaded media and save it into a request-owned temporary directory."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def prepare(self, files: list[UploadFile], target_directory: Path) -> list[PreparedMedia]:
        if not files:
            raise MediaPreparationError("MEDIA_EMPTY", "invalid_input")

        classified_uploads = [
            (
                upload,
                (upload.content_type or "").lower(),
                *classify_media(upload.content_type or "", self._settings),
            )
            for upload in files
        ]
        prepared_media: list[PreparedMedia] = []
        for index, (upload, content_type, upload_kind, suffix) in enumerate(
            classified_uploads,
            start=1,
        ):
            media_path = target_directory / f"original_{index:02d}{suffix}"
            sha256 = await self._save_upload(
                upload,
                media_path,
                self._settings.max_video_bytes if upload_kind == "video" else None,
            )
            prepared_media.append(
                PreparedMedia(
                    path=media_path,
                    content_type=content_type,
                    media_kind=upload_kind,
                    sha256=sha256,
                )
            )
        return prepared_media

    @staticmethod
    async def _save_upload(upload: UploadFile, target: Path, max_bytes: int | None) -> str:
        digest = hashlib.sha256()
        size = 0
        with target.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if max_bytes is not None and size > max_bytes:
                    raise MediaPreparationError("VIDEO_TOO_LARGE", "too_large")
                digest.update(chunk)
                output.write(chunk)
        if size == 0:
            raise MediaPreparationError("MEDIA_EMPTY", "invalid_input")
        return digest.hexdigest()
