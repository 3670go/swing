from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from httpx import HTTPError
from storage3.exceptions import StorageApiError
from supabase import Client, create_client

from app.config import Settings

SIGNED_UPLOAD_TTL_SECONDS = 2 * 60 * 60


@dataclass(frozen=True)
class SignedUpload:
    """Temporary credentials for a direct resumable Storage upload."""

    object_path: str
    upload_token: str
    resumable_endpoint: str
    expires_in_seconds: int = SIGNED_UPLOAD_TTL_SECONDS


class StorageSigner(Protocol):
    """Port used by the media upload service."""

    def create_signed_upload(self, object_path: str) -> SignedUpload:
        """Create a non-upserting signed upload token."""
        ...


class StorageSigningError(RuntimeError):
    """Supabase could not issue a usable upload credential."""


def build_resumable_endpoint(supabase_url: str) -> str:
    """Prefer Supabase's direct Storage hostname for resumable uploads."""
    parsed = urlparse(supabase_url)
    host = parsed.hostname
    if not host:
        raise ValueError("SUPABASE_URL must include a hostname")
    if host.endswith(".supabase.co"):
        project_ref = host.removesuffix(".supabase.co")
        return f"https://{project_ref}.storage.supabase.co/storage/v1/upload/resumable"
    return f"{supabase_url.rstrip('/')}/storage/v1/upload/resumable"


def _read_upload_token(response: Any) -> str:
    if isinstance(response, dict):
        token = response.get("token")
    else:
        token = getattr(response, "token", None)
    if not isinstance(token, str) or not token:
        raise ValueError("Supabase signed upload response did not include a token")
    return token


class SupabaseStorageSigner:
    """Server-side signer for direct uploads to a private Supabase bucket."""

    def __init__(self, settings: Settings, client: Client | None = None) -> None:
        self._bucket_name = settings.supabase_storage_bucket
        self._client = client or create_client(
            str(settings.supabase_url).rstrip("/"), settings.secret_key
        )
        self._resumable_endpoint = build_resumable_endpoint(str(settings.supabase_url))

    def create_signed_upload(self, object_path: str) -> SignedUpload:
        """Create a two-hour token without allowing object replacement."""
        try:
            response = self._client.storage.from_(self._bucket_name).create_signed_upload_url(
                object_path,
                options={"upsert": "false"},
            )
            upload_token = _read_upload_token(response)
        except (HTTPError, StorageApiError, ValueError) as error:
            raise StorageSigningError("Could not create a signed upload token") from error
        return SignedUpload(
            object_path=object_path,
            upload_token=upload_token,
            resumable_endpoint=self._resumable_endpoint,
        )

    def assert_bucket_access(self) -> None:
        """Verify that the configured private bucket is reachable by the server client."""
        bucket = self._client.storage.get_bucket(self._bucket_name)
        is_public = getattr(bucket, "public", None)
        if isinstance(bucket, dict):
            is_public = bucket.get("public")
        if is_public is not False:
            raise ValueError("Configured Supabase Storage bucket must be private")


class SupabaseMediaStore:
    """Server-only upload and deletion adapter for the private media bucket."""

    def __init__(self, settings: Settings, client: Client | None = None) -> None:
        self._bucket = (
            client or create_client(str(settings.supabase_url).rstrip("/"), settings.secret_key)
        ).storage.from_(settings.supabase_storage_bucket)

    def upload(self, object_path: str, local_path: Path, content_type: str) -> None:
        """Upload a new immutable media object."""
        try:
            with local_path.open("rb") as media_file:
                self._bucket.upload(
                    path=object_path,
                    file=media_file,
                    file_options={
                        "cache-control": "3600",
                        "content-type": content_type,
                        "upsert": "false",
                    },
                )
        except (HTTPError, StorageApiError) as error:
            raise StorageSigningError("Could not upload media to private Storage") from error

    def remove(self, object_path: str) -> None:
        """Delete one private object through the Storage API."""
        self.remove_many([object_path])

    def remove_many(self, object_paths: list[str]) -> None:
        """Delete private objects in one Storage API request."""
        if not object_paths:
            return
        try:
            self._bucket.remove(object_paths)
        except (HTTPError, StorageApiError) as error:
            raise StorageSigningError("Could not delete media from private Storage") from error
