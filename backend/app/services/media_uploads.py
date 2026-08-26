import uuid
from dataclasses import dataclass

from app.config import Settings
from app.database import Database
from app.repositories.media_assets import MediaAssetRepository
from app.storage import SignedUpload, StorageSigner, StorageSigningError

CONTENT_TYPE_SUFFIXES = {
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
}


@dataclass(frozen=True)
class CreateVideoUpload:
    """Validated technical input for one original swing video."""

    owner_context_id: uuid.UUID
    swing_session_id: uuid.UUID
    content_type: str
    size_bytes: int


@dataclass(frozen=True)
class VideoUploadIntent:
    """Metadata and temporary Storage credential returned to the API layer."""

    media_asset_id: uuid.UUID
    storage_bucket: str
    signed_upload: SignedUpload


class VideoUploadValidationError(ValueError):
    """The selected file does not satisfy the configured upload contract."""


class MediaUploadService:
    """Create metadata first, then issue a non-upserting Storage upload token."""

    def __init__(
        self,
        *,
        settings: Settings,
        database: Database,
        repository: MediaAssetRepository,
        storage_signer: StorageSigner,
    ) -> None:
        self._settings = settings
        self._database = database
        self._repository = repository
        self._storage_signer = storage_signer

    def create_video_upload(self, command: CreateVideoUpload) -> VideoUploadIntent:
        """Create a pending media row and a signed resumable upload credential."""
        suffix = self._validate_file(command.content_type, command.size_bytes)
        media_asset_id = uuid.uuid4()
        storage_path = f"original-video/{command.swing_session_id}/{media_asset_id}{suffix}"

        with self._database.session() as session:
            self._repository.create_pending_original_video(
                session,
                media_asset_id=media_asset_id,
                owner_context_id=command.owner_context_id,
                swing_session_id=command.swing_session_id,
                storage_path=storage_path,
            )

        try:
            signed_upload = self._storage_signer.create_signed_upload(storage_path)
        except StorageSigningError:
            with self._database.session() as session:
                self._repository.mark_failed(session, media_asset_id)
            raise

        return VideoUploadIntent(
            media_asset_id=media_asset_id,
            storage_bucket=self._settings.supabase_storage_bucket,
            signed_upload=signed_upload,
        )

    def _validate_file(self, content_type: str, size_bytes: int) -> str:
        if content_type not in self._settings.allowed_video_content_types:
            raise VideoUploadValidationError(f"Unsupported video content type: {content_type}")
        if size_bytes <= 0:
            raise VideoUploadValidationError("Video size must be positive")
        max_video_bytes = self._settings.max_video_bytes
        if max_video_bytes is not None and size_bytes > max_video_bytes:
            raise VideoUploadValidationError("Video exceeds the configured upload limit")
        return CONTENT_TYPE_SUFFIXES[content_type]
