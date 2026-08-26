from app.domain.models import CoachReply, ConversationReply


def render_conversation_reply(reply: ConversationReply) -> str:
    """Render only fields permitted on the chat surface."""
    parts = [reply.message.strip()]
    if reply.positive_feedback:
        parts.append(reply.positive_feedback.strip())
    if reply.follow_up_question:
        parts.append(reply.follow_up_question.strip())
    return "\n\n".join(parts)


def render_coach_reply(reply: CoachReply) -> str:
    """Render the user-facing conversation portion of an analysis reply."""
    return render_conversation_reply(reply.conversation)
