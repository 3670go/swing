import unittest
import uuid
from contextlib import contextmanager
from typing import Any

from app.config import Settings
from app.services.media_uploads import (
    CreateVideoUpload,
    MediaUploadService,
    VideoUploadValidationError,
)
from app.storage import SignedUpload, StorageSigningError


class FakeDatabase:
    def __init__(self) -> None:
        self.transactions = 0

    @contextmanager
    def session(self) -> Any:
        self.transactions += 1
        yield object()


class FakeRepository:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.failed: list[uuid.UUID] = []

    def create_pending_original_video(self, session: Any, **values: Any) -> object:
        self.created.append(values)
        return object()

    def mark_failed(self, session: Any, media_asset_id: uuid.UUID) -> None:
        self.failed.append(media_asset_id)


class FakeStorageSigner:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.paths: list[str] = []

    def create_signed_upload(self, object_path: str) -> SignedUpload:
        self.paths.append(object_path)
        if self.should_fail:
            raise StorageSigningError("test failure")
        return SignedUpload(
            object_path=object_path,
            upload_token="temporary-token",
            resumable_endpoint="https://project.storage.supabase.co/storage/v1/upload/resumable",
        )


def make_settings(*, max_video_bytes: int | None = None) -> Settings:
    return Settings(
        database_url="postgresql://user:secret@host:6543/postgres",
        supabase_url="https://project.supabase.co",
        supabase_secret_key="server-secret-key",
        max_video_bytes=max_video_bytes,
    )


class MediaUploadServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = FakeDatabase()
        self.repository = FakeRepository()
        self.storage = FakeStorageSigner()
        self.service = MediaUploadService(
            settings=make_settings(),
            database=self.database,  # type: ignore[arg-type]
            repository=self.repository,  # type: ignore[arg-type]
            storage_signer=self.storage,
        )

    def test_creates_private_resumable_video_intent(self) -> None:
        owner_context_id = uuid.uuid4()
        swing_session_id = uuid.uuid4()

        result = self.service.create_video_upload(
            CreateVideoUpload(
                owner_context_id=owner_context_id,
                swing_session_id=swing_session_id,
                content_type="video/mp4",
                size_bytes=12_000_000,
            )
        )

        self.assertEqual(result.storage_bucket, "swing-media")
        self.assertEqual(result.signed_upload.upload_token, "temporary-token")
        self.assertEqual(self.database.transactions, 1)
        self.assertEqual(self.repository.created[0]["owner_context_id"], owner_context_id)
        self.assertTrue(result.signed_upload.object_path.endswith(".mp4"))
        self.assertIn(str(swing_session_id), result.signed_upload.object_path)

    def test_rejects_video_above_limit_before_database_write(self) -> None:
        service = MediaUploadService(
            settings=make_settings(max_video_bytes=1_000_000),
            database=self.database,  # type: ignore[arg-type]
            repository=self.repository,  # type: ignore[arg-type]
            storage_signer=self.storage,
        )

        with self.assertRaises(VideoUploadValidationError):
            service.create_video_upload(
                CreateVideoUpload(
                    owner_context_id=uuid.uuid4(),
                    swing_session_id=uuid.uuid4(),
                    content_type="video/mp4",
                    size_bytes=1_000_001,
                )
            )

        self.assertEqual(self.database.transactions, 0)
        self.assertEqual(self.repository.created, [])

    def test_marks_metadata_failed_when_storage_signing_fails(self) -> None:
        failing_storage = FakeStorageSigner(should_fail=True)
        service = MediaUploadService(
            settings=make_settings(),
            database=self.database,  # type: ignore[arg-type]
            repository=self.repository,  # type: ignore[arg-type]
            storage_signer=failing_storage,
        )

        with self.assertRaises(StorageSigningError):
            service.create_video_upload(
                CreateVideoUpload(
                    owner_context_id=uuid.uuid4(),
                    swing_session_id=uuid.uuid4(),
                    content_type="video/webm",
                    size_bytes=1_000_000,
                )
            )

        self.assertEqual(self.database.transactions, 2)
        self.assertEqual(len(self.repository.failed), 1)


if __name__ == "__main__":
    unittest.main()
