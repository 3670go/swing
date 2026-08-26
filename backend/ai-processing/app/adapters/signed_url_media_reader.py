import asyncio
import hashlib
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.config import Settings
from app.ports.media_reader import DownloadedMedia, RemoteMediaReference
from app.services.media_preparation import MediaPreparationError, classify_media

DOWNLOAD_CHUNK_BYTES = 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 30


class MediaReaderError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


class SignedUrlMediaReader:
    """Download one Supabase signed URL without logging or following redirects."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._allowed_host = (urlsplit(str(settings.supabase_url)).hostname or "").lower()

    async def read(
        self,
        media: RemoteMediaReference,
        destination_directory: Path,
    ) -> DownloadedMedia:
        return await asyncio.to_thread(self._read, media, destination_directory)

    def _read(
        self,
        media: RemoteMediaReference,
        destination_directory: Path,
    ) -> DownloadedMedia:
        parsed = urlsplit(media.read_url)
        if parsed.scheme != "https" or (parsed.hostname or "").lower() != self._allowed_host:
            raise MediaReaderError("MEDIA_UNAVAILABLE", "Media URL host is not approved")

        try:
            detected_kind, suffix = classify_media(media.content_type, self._settings)
        except MediaPreparationError as error:
            raise MediaReaderError("MEDIA_TYPE_UNSUPPORTED", "Unsupported media type") from error
        if detected_kind != media.kind:
            raise MediaReaderError(
                "MEDIA_TYPE_UNSUPPORTED",
                "Media kind does not match content type",
            )

        destination = destination_directory / f"{media.media_id}{suffix}"
        digest = hashlib.sha256()
        downloaded_bytes = 0
        request = Request(media.read_url, headers={"User-Agent": "swing-analyzer-internal/1.0"})
        try:
            with (
                build_opener(_NoRedirectHandler()).open(
                    request,
                    timeout=DOWNLOAD_TIMEOUT_SECONDS,
                ) as response,
                destination.open("wb") as output,
            ):
                while chunk := response.read(DOWNLOAD_CHUNK_BYTES):
                    downloaded_bytes += len(chunk)
                    if downloaded_bytes > media.size_bytes:
                        raise MediaReaderError(
                            "MEDIA_UNAVAILABLE",
                            "Downloaded media exceeds declared size",
                        )
                    digest.update(chunk)
                    output.write(chunk)
        except MediaReaderError:
            destination.unlink(missing_ok=True)
            raise
        except (HTTPError, URLError, OSError) as error:
            destination.unlink(missing_ok=True)
            raise MediaReaderError("MEDIA_UNAVAILABLE", "Media download failed") from error

        if downloaded_bytes != media.size_bytes or digest.hexdigest() != media.sha256:
            destination.unlink(missing_ok=True)
            raise MediaReaderError("MEDIA_UNAVAILABLE", "Media integrity check failed")
        return DownloadedMedia(
            path=destination,
            kind=media.kind,
            content_type=media.content_type,
        )
