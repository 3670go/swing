import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.domain.analysis_status import REPLY_AVAILABLE_STATUSES
from app.models import AnalysisRun, ChatMessage


class ChatMessageRepository:
    """Persistence for user-visible conversation messages."""

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
        self,
        session: Session,
        conversation_id: uuid.UUID,
        *,
        limit: int = 12,
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
                AnalysisRun.status.in_(REPLY_AVAILABLE_STATUSES),
            )
            .order_by(desc(AnalysisRun.completed_at))
            .limit(1)
        )
        return run.reply_json if run is not None else None
