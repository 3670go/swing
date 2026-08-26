import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, select, update
from sqlalchemy.orm import Session

from app.domain.analysis_status import (
    DELETED_STATUS,
    AnalysisCompletionStatus,
    AnalysisStatusPolicy,
)
from app.domain.models import CoachReply, ShotContext, VisionObservation
from app.models import AnalysisRun, Conversation, MediaAsset, SwingSession


class SwingAnalysisRepository:
    """Persistence for swing sessions, analysis runs, and their original media."""

    def create_swing_session(
        self,
        session: Session,
        *,
        owner_id: uuid.UUID,
        conversation_id: uuid.UUID,
        context: ShotContext,
        question: str | None,
    ) -> SwingSession:
        swing_session = SwingSession(
            owner_context_id=owner_id,
            conversation_id=conversation_id,
            shot_profile=context.shot_profile,
            club=context.club,
            camera_view=context.camera_view,
            handedness=context.handedness,
            user_question=question or None,
            user_feel=None,
            shot_result_json={"value": context.shot_result} if context.shot_result else None,
        )
        session.add(swing_session)
        session.flush()
        return swing_session

    def create_analysis_run(
        self,
        session: Session,
        *,
        swing_session_id: uuid.UUID,
        conversation_id: uuid.UUID,
        media_kind: str,
        model: str,
    ) -> AnalysisRun:
        run = AnalysisRun(
            swing_session_id=swing_session_id,
            conversation_id=conversation_id,
            status=AnalysisStatusPolicy.start(),
            media_kind=media_kind,
            model=model,
        )
        session.add(run)
        session.flush()
        session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(active_analysis_run_id=run.id, updated_at=datetime.now(UTC))
        )
        return run

    def create_uploaded_media(
        self,
        session: Session,
        *,
        media_asset_id: uuid.UUID,
        swing_session_id: uuid.UUID,
        media_kind: str,
        storage_path: str,
        sha256: str,
    ) -> MediaAsset:
        asset = MediaAsset(
            id=media_asset_id,
            session_id=swing_session_id,
            kind=f"original_{media_kind}",
            storage_path=storage_path,
            sha256=sha256,
            status="uploaded",
        )
        session.add(asset)
        session.flush()
        return asset

    def finish_analysis(
        self,
        session: Session,
        *,
        run_id: uuid.UUID,
        status: AnalysisCompletionStatus,
        observation: VisionObservation,
        reply: CoachReply | None,
    ) -> None:
        transition = AnalysisStatusPolicy.complete(status)
        session.execute(
            update(AnalysisRun)
            .where(
                AnalysisRun.id == run_id,
                AnalysisRun.status.in_(transition.allowed_from),
            )
            .values(
                status=transition.target,
                observation_json=observation.model_dump(mode="json"),
                reply_json=reply.model_dump(mode="json") if reply else None,
                completed_at=datetime.now(UTC),
            )
        )

    def fail_analysis(self, session: Session, run_id: uuid.UUID, error_code: str) -> None:
        transition = AnalysisStatusPolicy.fail()
        session.execute(
            update(AnalysisRun)
            .where(
                AnalysisRun.id == run_id,
                AnalysisRun.status.in_(transition.allowed_from),
            )
            .values(
                status=transition.target,
                error_code=error_code,
                completed_at=datetime.now(UTC),
            )
        )

    def history(
        self,
        session: Session,
        *,
        owner_id: uuid.UUID,
        limit: int = 20,
    ) -> list[tuple[AnalysisRun, SwingSession]]:
        rows = session.execute(
            select(AnalysisRun, SwingSession)
            .join(SwingSession, SwingSession.id == AnalysisRun.swing_session_id)
            .where(
                SwingSession.owner_context_id == owner_id,
                AnalysisRun.status != DELETED_STATUS,
            )
            .order_by(desc(AnalysisRun.created_at))
            .limit(limit)
        )
        return list(rows.tuples())

    def owned_run_with_assets(
        self,
        session: Session,
        *,
        run_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> tuple[AnalysisRun, list[MediaAsset]] | None:
        rows = session.execute(
            select(AnalysisRun, MediaAsset)
            .join(SwingSession, SwingSession.id == AnalysisRun.swing_session_id)
            .join(MediaAsset, MediaAsset.session_id == SwingSession.id)
            .where(
                AnalysisRun.id == run_id,
                SwingSession.owner_context_id == owner_id,
                AnalysisRun.status != DELETED_STATUS,
            )
        ).all()
        if not rows:
            return None
        return rows[0][0], [row[1] for row in rows]

    def mark_deleted(
        self,
        session: Session,
        *,
        run_id: uuid.UUID,
        media_asset_ids: list[uuid.UUID],
    ) -> None:
        transition = AnalysisStatusPolicy.delete()
        session.execute(
            update(AnalysisRun)
            .where(
                AnalysisRun.id == run_id,
                AnalysisRun.status.in_(transition.allowed_from),
            )
            .values(status=transition.target, reply_json=None, observation_json=None)
        )
        session.execute(
            update(MediaAsset)
            .where(MediaAsset.id.in_(media_asset_ids))
            .values(status=DELETED_STATUS)
        )
