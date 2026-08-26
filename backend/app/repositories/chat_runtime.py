import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select, update
from sqlalchemy.orm import Session

from app.models import (
    AnalysisRun,
    ChatMessage,
    Conversation,
    MediaAsset,
    OwnerContext,
    SwingSession,
)
from app.schemas import CoachReply, ShotContext, VisionObservation


class OwnerAccessError(LookupError):
    """The requested resource does not belong to the anonymous owner."""


class ChatRuntimeRepository:
    """Canonical persistence for anonymous conversations and analysis runs."""

    def get_or_create_owner(self, session: Session, anonymous_session_hash: str) -> OwnerContext:
        owner = session.scalar(
            select(OwnerContext).where(
                OwnerContext.anonymous_session_hash == anonymous_session_hash
            )
        )
        if owner is not None:
            return owner
        owner = OwnerContext(anonymous_session_hash=anonymous_session_hash)
        session.add(owner)
        session.flush()
        return owner

    def get_or_create_conversation(
        self,
        session: Session,
        *,
        owner: OwnerContext,
        conversation_id: uuid.UUID | None,
        context: ShotContext,
    ) -> Conversation:
        if conversation_id is not None:
            conversation = session.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.owner_context_id == owner.id,
                )
            )
            if conversation is None:
                raise OwnerAccessError("Conversation was not found for this owner")
        else:
            conversation = Conversation(owner_context_id=owner.id)
            session.add(conversation)
            session.flush()

        conversation.shot_profile = context.shot_profile
        conversation.club = context.club
        conversation.analysis_goal = context.analysis_goal
        conversation.updated_at = datetime.now(UTC)
        return conversation

    def add_message(
        self,
        session: Session,
        *,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        analysis_run_id: uuid.UUID | None = None,
        interaction_meta: dict[str, Any] | None = None,
    ) -> ChatMessage:
        message = ChatMessage(
            conversation_id=conversation_id,
            analysis_run_id=analysis_run_id,
            role=role,
            content=content,
            interaction_meta_json=interaction_meta,
        )
        session.add(message)
        session.flush()
        return message

    def recent_messages(
        self, session: Session, conversation_id: uuid.UUID, *, limit: int = 12
    ) -> list[dict[str, Any]]:
        messages = list(
            session.scalars(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conversation_id)
                .order_by(desc(ChatMessage.created_at))
                .limit(limit)
            )
        )
        return [
            {
                "role": message.role,
                "content": message.content,
                "interaction_meta": message.interaction_meta_json,
            }
            for message in reversed(messages)
        ]

    def latest_reply(self, session: Session, conversation_id: uuid.UUID) -> dict[str, Any] | None:
        run = session.scalar(
            select(AnalysisRun)
            .where(
                AnalysisRun.conversation_id == conversation_id,
                AnalysisRun.status.in_(("succeeded", "limited")),
            )
            .order_by(desc(AnalysisRun.completed_at))
            .limit(1)
        )
        return run.reply_json if run is not None else None

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
            user_feel=question or None,
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
            status="running",
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
        status: str,
        observation: VisionObservation,
        reply: CoachReply | None,
    ) -> None:
        session.execute(
            update(AnalysisRun)
            .where(AnalysisRun.id == run_id, AnalysisRun.status == "running")
            .values(
                status=status,
                observation_json=observation.model_dump(mode="json"),
                reply_json=reply.model_dump(mode="json") if reply else None,
                completed_at=datetime.now(UTC),
            )
        )

    def fail_analysis(self, session: Session, run_id: uuid.UUID, error_code: str) -> None:
        session.execute(
            update(AnalysisRun)
            .where(AnalysisRun.id == run_id, AnalysisRun.status == "running")
            .values(
                status="failed",
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
                AnalysisRun.status != "deleted",
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
                AnalysisRun.status != "deleted",
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
        session.execute(
            update(AnalysisRun)
            .where(AnalysisRun.id == run_id)
            .values(status="deleted", reply_json=None, observation_json=None)
        )
        session.execute(
            update(MediaAsset).where(MediaAsset.id.in_(media_asset_ids)).values(status="deleted")
        )
