from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol
from uuid import UUID


@dataclass(frozen=True)
class RemoteMediaReference:
    media_id: UUID
    kind: Literal["photo", "video"]
    content_type: str
    size_bytes: int
    sha256: str
    read_url: str


@dataclass(frozen=True)
class DownloadedMedia:
    path: Path
    kind: Literal["photo", "video"]
    content_type: str


class MediaReader(Protocol):
    """Read one approved remote media object into request-scoped storage."""

    async def read(
        self,
        media: RemoteMediaReference,
        destination_directory: Path,
    ) -> DownloadedMedia: ...
