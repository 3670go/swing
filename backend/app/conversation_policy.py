from dataclasses import asdict, dataclass
from typing import Any, Literal

from app.schemas import CoachContent, ConversationReply

InviteMode = Literal[
    "compare_good_bad",
    "locate_timing",
    "recall_specific_shot",
    "connect_body_feel",
    "follow_up_experiment",
]
ResponseMode = Literal["short", "standard", "deep"]
ConversationTone = Literal["casual", "polite"]

INVITE_MODES: tuple[InviteMode, ...] = (
    "compare_good_bad",
    "locate_timing",
    "recall_specific_shot",
    "connect_body_feel",
    "follow_up_experiment",
)
STRENGTH_REQUEST_TERMS = (
    "장점",
    "좋은 점",
    "좋은점",
    "잘된 점",
    "잘된점",
    "강점",
    "뭐가 좋아",
)
DEEP_RESPONSE_TERMS = (
    "자세히",
    "전체 분석",
    "전체적으로",
    "비교해",
    "기준",
    "원리",
    "왜 그런지",
)
CONTRAST_TERMS = ("잘 맞", "안 맞", "덜 그래", "더 심", "때만", "날에는")
TIMING_TERMS = ("전환", "탑에서", "내려올 때", "공 맞", "임팩트")
EXPERIMENT_TERMS = ("해봤", "연습해", "바꿔봤", "드릴", "시도했")
OPEN_GOAL_TERMS = ("잘 치고", "실력 늘", "프로처럼", "매킬로이처럼", "닮고 싶")
POLITE_TERMS = ("요", "습니다", "주세요", "부탁합니다", "궁금합니다")
CONTEXT_RELEVANCE_TERMS = (
    "드라이버",
    "아이언",
    "우드",
    "유틸리티",
    "웨지",
    "풀스윙",
    "숏게임",
    "어프로치",
    "칩",
    "피치",
    "벙커",
    "정면",
    "후방",
    "dtl",
    "face on",
    "자세",
    "구질",
    "미스",
    "샷 결과",
    "스윙 영상",
)
INTERNAL_SURFACE_TERMS = (
    "observation",
    "measurement",
    "feel 대조",
    "evidence_boundary",
    "baseassessment",
    "coachcontent",
    "conversationreply",
    "response_policy",
    "판정 불가 목록",
    "내부 제어",
    "백엔드",
)
FALLBACK_QUESTIONS: dict[InviteMode, str] = {
    "compare_good_bad": "잘 맞은 샷과 안 맞은 샷에서는 어떤 느낌이 가장 달랐어?",
    "locate_timing": "그 느낌이 가장 강한 순간은 전환할 때야, 공 맞을 때야?",
    "recall_specific_shot": "최근 가장 심했던 샷은 공이 어디로 출발했어?",
    "connect_body_feel": "영상에서 보인 순간이 네 몸에서도 같은 순간으로 느껴졌어?",
    "follow_up_experiment": "그 실험에서는 몸 느낌과 샷 결과 중 무엇부터 달라졌어?",
}


@dataclass(frozen=True)
class ConversationPolicy:
    """Deterministic limits applied before and after conversational composition."""

    response_mode: ResponseMode
    question_allowed: bool
    question_preferred: bool
    preferred_invite_mode: InviteMode | None
    positive_allowed: bool
    allowed_invite_modes: tuple[InviteMode, ...]
    blocked_positive_topics: tuple[str, ...]
    user_detail_anchor: str
    context_relevant: bool
    tone: ConversationTone

    def prompt_payload(self) -> dict[str, Any]:
        return asdict(self)


def _assistant_metadata(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metadata: list[dict[str, Any]] = []
    for item in history:
        if item.get("role") != "assistant":
            continue
        interaction_meta = item.get("interaction_meta")
        metadata.append(interaction_meta if isinstance(interaction_meta, dict) else {})
    return metadata


def _response_mode(message: str) -> ResponseMode:
    normalized = message.strip()
    if any(term in normalized for term in DEEP_RESPONSE_TERMS) or len(normalized) >= 180:
        return "deep"
    if len(normalized) <= 50 and "\n" not in normalized:
        return "short"
    return "standard"


def build_conversation_policy(
    *,
    message: str,
    history: list[dict[str, Any]],
    latest_analysis: dict[str, Any] | None,
) -> ConversationPolicy:
    """Calculate cadence and evidence limits without asking the model to self-police."""
    assistant_metadata = _assistant_metadata(history)
    recent_questions = assistant_metadata[-2:]
    question_allowed = not (
        len(recent_questions) == 2 and all(item.get("question_topic") for item in recent_questions)
    )
    preferred_invite_mode: InviteMode | None = None
    if question_allowed:
        if any(term in message for term in CONTRAST_TERMS):
            preferred_invite_mode = "compare_good_bad"
        elif any(term in message for term in EXPERIMENT_TERMS):
            preferred_invite_mode = "follow_up_experiment"
        elif any(term in message for term in TIMING_TERMS):
            preferred_invite_mode = "locate_timing"
        elif any(term in message for term in OPEN_GOAL_TERMS):
            preferred_invite_mode = "recall_specific_shot"

    recent_positive = assistant_metadata[-3:]
    explicit_strength_request = any(term in message for term in STRENGTH_REQUEST_TERMS)
    positive_allowed = latest_analysis is not None and (
        explicit_strength_request or not any(item.get("positive_topic") for item in recent_positive)
    )
    blocked_positive_topics = tuple(
        str(item["positive_topic"])
        for item in assistant_metadata[-5:]
        if item.get("positive_topic")
    )

    return ConversationPolicy(
        response_mode=_response_mode(message),
        question_allowed=question_allowed,
        question_preferred=preferred_invite_mode is not None,
        preferred_invite_mode=preferred_invite_mode,
        positive_allowed=positive_allowed,
        allowed_invite_modes=INVITE_MODES if question_allowed else (),
        blocked_positive_topics=blocked_positive_topics,
        user_detail_anchor=message.strip()[:180],
        context_relevant=any(term in message.strip().lower() for term in CONTEXT_RELEVANCE_TERMS),
        tone="polite" if any(term in message.strip() for term in POLITE_TERMS) else "casual",
    )


def enforce_conversation_policy(
    reply: ConversationReply,
    policy: ConversationPolicy,
    content: CoachContent,
) -> tuple[ConversationReply, dict[str, Any]]:
    """Drop optional model output that violates deterministic conversation policy."""
    updates: dict[str, Any] = {}

    normalized_message = reply.message.lower()
    surface_valid = not any(term in normalized_message for term in INTERNAL_SURFACE_TERMS)
    surface_valid = surface_valid and "?" not in reply.message
    if not surface_valid:
        updates["message"] = content.direct_answer

    positive_valid = (
        policy.positive_allowed
        and reply.positive_feedback is not None
        and reply.positive_topic is not None
        and content.preserve_candidate is not None
        and content.preserve_topic is not None
        and reply.positive_topic == content.preserve_topic
        and reply.positive_topic not in policy.blocked_positive_topics
    )
    if not positive_valid:
        updates.update(positive_feedback=None, positive_topic=None)

    question_valid = (
        policy.question_allowed
        and reply.follow_up_question is not None
        and reply.question_topic is not None
        and reply.invite_mode in policy.allowed_invite_modes
        and reply.follow_up_question.count("?") <= 1
    )
    if not question_valid:
        if policy.question_preferred and policy.preferred_invite_mode is not None:
            preferred_mode = policy.preferred_invite_mode
            updates.update(
                follow_up_question=FALLBACK_QUESTIONS[preferred_mode],
                question_topic=f"policy_{preferred_mode}",
                invite_mode=preferred_mode,
            )
        else:
            updates.update(
                follow_up_question=None,
                question_topic=None,
                invite_mode="none",
            )

    enforced = reply.model_copy(update=updates)
    interaction_meta = {
        "response_mode": policy.response_mode,
        "positive_topic": enforced.positive_topic,
        "question_topic": enforced.question_topic,
        "invite_mode": enforced.invite_mode,
    }
    return enforced, interaction_meta
