import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import MediaAsset, SwingSession


class SwingSessionOwnershipError(LookupError):
    """The swing session does not exist under the supplied owner context."""


class MediaAssetRepository:
    """Persistence operations for private media metadata."""

    def create_pending_original_video(
        self,
        session: Session,
        *,
        media_asset_id: uuid.UUID,
        owner_context_id: uuid.UUID,
        swing_session_id: uuid.UUID,
        storage_path: str,
    ) -> MediaAsset:
        """Insert a pending asset only when the owner owns the swing session."""
        owned_session_id = session.scalar(
            select(SwingSession.id).where(
                SwingSession.id == swing_session_id,
                SwingSession.owner_context_id == owner_context_id,
            )
        )
        if owned_session_id is None:
            raise SwingSessionOwnershipError("Swing session was not found for this owner")

        asset = MediaAsset(
            id=media_asset_id,
            session_id=swing_session_id,
            kind="original_video",
            storage_path=storage_path,
            status="pending_upload",
        )
        session.add(asset)
        session.flush()
        return asset

    def mark_failed(self, session: Session, media_asset_id: uuid.UUID) -> None:
        """Record that signed upload preparation failed."""
        session.execute(
            update(MediaAsset)
            .where(
                MediaAsset.id == media_asset_id,
                MediaAsset.status == "pending_upload",
            )
            .values(status="failed")
        )

    def mark_uploaded(
        self,
        session: Session,
        *,
        media_asset_id: uuid.UUID,
        owner_context_id: uuid.UUID,
        sha256: str,
        duration_ms: int,
        width: int,
        height: int,
    ) -> None:
        """Complete metadata after Storage object and owner verification."""
        owned_asset_id = session.scalar(
            select(MediaAsset.id)
            .join(SwingSession, SwingSession.id == MediaAsset.session_id)
            .where(
                MediaAsset.id == media_asset_id,
                SwingSession.owner_context_id == owner_context_id,
                MediaAsset.status == "pending_upload",
            )
        )
        if owned_asset_id is None:
            raise SwingSessionOwnershipError("Pending media asset was not found for this owner")

        session.execute(
            update(MediaAsset)
            .where(MediaAsset.id == media_asset_id)
            .values(
                sha256=sha256,
                duration_ms=duration_ms,
                width=width,
                height=height,
                status="uploaded",
            )
        )
