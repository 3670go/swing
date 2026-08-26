import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import ShotContext
from app.models import Conversation, OwnerContext


class OwnerAccessError(LookupError):
    """The requested resource does not belong to the anonymous owner."""


class OwnerConversationRepository:
    """Persistence for anonymous owners and their conversation boundaries."""

    def find_owner(self, session: Session, anonymous_session_hash: str) -> OwnerContext | None:
        return session.scalar(
            select(OwnerContext).where(
                OwnerContext.anonymous_session_hash == anonymous_session_hash
            )
        )

    def get_or_create_owner(self, session: Session, anonymous_session_hash: str) -> OwnerContext:
        owner = self.find_owner(session, anonymous_session_hash)
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
