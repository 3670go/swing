"""결정적 신호 추출.

LLM 을 호출하지 않는다. 모든 신호는 입력에 실재하는 ID 를 근거로 가진다.
활성 코칭 주제가 있으면 그 주제에 속한 메시지·이벤트·피드백만 사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from baseline import is_bare_acknowledgement
from schemas import (
    BehaviorEvent,
    BehaviorEventType,
    Confidence,
    ConversationInput,
    EvidenceReference,
    EvidenceSourceType,
    ExplicitIntent,
    FeedbackEvent,
    FeedbackType,
    Message,
    ProgressLevel,
    VideoAnalysisEvidence,
    VideoComparison,
    min_confidence,
)

CAUSE_TOKENS = ("왜", "이유", "원인", "때문")
COMPARISON_TOKENS = ("비교", "차이", "전보다", "예전", "다른점", "다른 점")
PROGRESS_CHECK_TOKENS = ("나아졌", "좋아졌", "늘었", "발전", "얼마나")
DIRECTION_TOKENS = ("맞나", "맞는", "맞을까", "맞아?", "이게 맞", "제대로 하", "이렇게 하는")
CORRECTION_TOKENS = ("어떻게", "고치", "교정", "방법", "해야", "연습법", "뭘 하")
QUESTION_TOKENS = ("?", "나요", "까요", "가요", "어때")

PROGRESS_REPORT_TOKENS = (
    "해보니",
    "해봤",
    "해보니까",
    "좋아졌",
    "잘 맞",
    "잘맞",
    "잘 됐",
    "잘됐",
    "줄었",
    "나아졌",
    "된다",
    "됐어",
    "괜찮아졌",
)
DIFFICULTY_TOKENS = ("어려워", "어렵", "이해가 안", "무슨 말", "복잡", "모르겠")
LENGTH_COMPLAINT_TOKENS = ("너무 길", "길어", "짧게")
ACTIONABLE_TOKENS = ("뭐부터", "어떻게 연습", "연습법", "당장", "지금 뭐")
CORRECTION_OF_INFERENCE_TOKENS = ("아니라", "그게 아니", "말고")

VIDEO_MIN_PROMOTION_CONFIDENCE = Confidence.MEDIUM
"""영상 비교로 근거 수준을 올리기 위한 최소 입력 신뢰도. LOW 는 승격하지 않는다."""


# --------------------------------------------------------------------------
# Topic scope
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Scope:
    """활성 코칭 주제로 좁힌 입력 뷰. 원본은 변경하지 않는다."""

    topic_id: str | None
    messages: list[Message]
    behavior_events: list[BehaviorEvent]
    feedback_events: list[FeedbackEvent]
    video_evidence: list[VideoAnalysisEvidence]
    all_video_evidence: list[VideoAnalysisEvidence]
    latest_user_message: Message
    previous_user_message: Message | None

    def user_messages(self) -> list[Message]:
        return [m for m in self.messages if m.role == "user"]


def last_user_message(payload: ConversationInput) -> Message:
    for message in reversed(payload.messages):
        if message.role == "user":
            return message
    raise ValueError("no user message")  # ConversationInput validator 가 먼저 막는다


def build_scope(payload: ConversationInput) -> Scope:
    """활성 주제가 있으면 그 주제 것만 남긴다.

    현재 사용자 메시지는 이번 turn 의 입력이므로 주제 필터와 무관하게 항상 포함한다.
    """
    latest = last_user_message(payload)
    topic_id = payload.active_coaching_topic.topic_id if payload.active_coaching_topic else None

    if topic_id is None:
        messages = list(payload.messages)
        behavior_events = list(payload.behavior_events)
        feedback_events = list(payload.feedback_events)
    else:
        messages = [
            m
            for m in payload.messages
            if m.topic_id == topic_id or m.message_id == latest.message_id
        ]
        behavior_events = [e for e in payload.behavior_events if e.topic_id == topic_id]
        feedback_events = [e for e in payload.feedback_events if e.topic_id == topic_id]

    scoped_users = [m for m in messages if m.role == "user"]
    previous = scoped_users[-2] if len(scoped_users) >= 2 else None
    return Scope(
        topic_id=topic_id,
        messages=messages,
        behavior_events=behavior_events,
        feedback_events=feedback_events,
        video_evidence=list(payload.video_evidence),
        all_video_evidence=list(payload.video_evidence),
        latest_user_message=latest,
        previous_user_message=previous,
    )


# --------------------------------------------------------------------------
# Evidence helpers
# --------------------------------------------------------------------------


def message_ref(message: Message) -> EvidenceReference:
    return EvidenceReference(source_type=EvidenceSourceType.MESSAGE, source_id=message.message_id)


def behavior_ref(event: BehaviorEvent) -> EvidenceReference:
    return EvidenceReference(
        source_type=EvidenceSourceType.BEHAVIOR_EVENT, source_id=event.event_id
    )


def feedback_ref(event: FeedbackEvent) -> EvidenceReference:
    return EvidenceReference(
        source_type=EvidenceSourceType.FEEDBACK_EVENT, source_id=event.feedback_id
    )


def video_ref(evidence: VideoAnalysisEvidence) -> EvidenceReference:
    return EvidenceReference(
        source_type=EvidenceSourceType.VIDEO_ANALYSIS, source_id=evidence.analysis_id
    )


# --------------------------------------------------------------------------
# Explicit intent
# --------------------------------------------------------------------------


def _is_question(text: str) -> bool:
    return any(token in text for token in QUESTION_TOKENS)


def detect_explicit_intent(text: str) -> ExplicitIntent:
    """사용자가 직접 말한 요청만 판정한다. 추정하지 않는다."""
    if is_bare_acknowledgement(text):
        return ExplicitIntent.UNKNOWN
    if any(token in text for token in CAUSE_TOKENS):
        return ExplicitIntent.CAUSE_EXPLANATION
    if any(token in text for token in COMPARISON_TOKENS):
        return ExplicitIntent.COMPARISON
    if _is_question(text) and any(token in text for token in PROGRESS_CHECK_TOKENS):
        return ExplicitIntent.PROGRESS_CHECK
    if _is_question(text) and any(token in text for token in DIRECTION_TOKENS):
        return ExplicitIntent.DIRECTION_CONFIRMATION
    if any(token in text for token in CORRECTION_TOKENS):
        return ExplicitIntent.CORRECTION_ACTION
    if _is_question(text):
        return ExplicitIntent.GENERAL_QUESTION
    return ExplicitIntent.UNKNOWN


# --------------------------------------------------------------------------
# Progress
# --------------------------------------------------------------------------


def user_reported_progress_messages(scope: Scope) -> list[Message]:
    return [
        message
        for message in scope.messages
        if message.role == "user" and any(t in message.text for t in PROGRESS_REPORT_TOKENS)
    ]


def outcome_feedback(scope: Scope) -> list[FeedbackEvent]:
    return [
        event
        for event in scope.feedback_events
        if event.feedback_type is FeedbackType.ACTUALLY_IMPROVED
    ]


def practice_report_events(scope: Scope) -> list[BehaviorEvent]:
    return [
        event
        for event in scope.behavior_events
        if event.event_type is BehaviorEventType.PRACTICE_RESULT_REPORTED
    ]


@dataclass(frozen=True)
class ResultOccurrence:
    """하나의 연습 결과 보고. 행동 이벤트와 피드백이 같은 결과를 가리키면 하나로 센다."""

    anchor_id: str
    reference: EvidenceReference
    reported_at: str


def _feedback_anchor(scope: Scope, feedback: FeedbackEvent) -> str:
    """피드백이 가리키는 결과의 anchor.

    피드백 대상은 assistant 메시지다. 결과 보고는 보통 그 다음 사용자 메시지이므로,
    그 사용자 메시지를 anchor 로 삼아 행동 이벤트와 같은 결과인지 맞춘다.
    """
    ids = [m.message_id for m in scope.messages]
    if feedback.target_message_id in ids:
        index = ids.index(feedback.target_message_id)
        for message in scope.messages[index + 1 :]:
            if message.role == "user":
                return message.message_id
    return feedback.target_message_id


def result_occurrences(scope: Scope) -> list[ResultOccurrence]:
    """서로 다른 결과 보고만 남긴다. 같은 anchor 는 한 번으로 센다."""
    occurrences: dict[str, ResultOccurrence] = {}
    for event in practice_report_events(scope):
        anchor = event.related_message_id or event.event_id
        occurrences.setdefault(
            anchor,
            ResultOccurrence(anchor, behavior_ref(event), event.created_at.isoformat()),
        )
    for feedback in outcome_feedback(scope):
        anchor = _feedback_anchor(scope, feedback)
        occurrences.setdefault(
            anchor,
            ResultOccurrence(anchor, feedback_ref(feedback), feedback.created_at.isoformat()),
        )
    return sorted(occurrences.values(), key=lambda o: (o.reported_at, o.anchor_id))


def eligible_improved_video(scope: Scope) -> list[VideoAnalysisEvidence]:
    """근거 수준을 올릴 수 있는 영상만 남긴다.

    비교 대상이 명시되고 그 분석이 입력에 실재하며 입력 신뢰도가 MEDIUM 이상이어야 한다.
    """
    known = {v.analysis_id for v in scope.all_video_evidence}
    eligible: list[VideoAnalysisEvidence] = []
    for evidence in scope.video_evidence:
        if evidence.comparison is not VideoComparison.IMPROVED:
            continue
        compared = evidence.compared_to_analysis_id
        if compared is None or compared == evidence.analysis_id or compared not in known:
            continue
        if evidence.confidence is Confidence.LOW:
            continue
        eligible.append(evidence)
    return eligible


def classify_progress_level(
    scope: Scope,
) -> tuple[ProgressLevel, list[EvidenceReference], str, Confidence]:
    """근거 수준과 그 수준의 신뢰도를 판정한다.

    사용자 보고는 사용자 보고로만 남고 실제 스윙 개선으로 승격되지 않는다.
    영상 승격은 비교 대상과 MEDIUM 이상 신뢰도를 모두 만족할 때만 일어나며,
    결과 신뢰도는 입력 영상 신뢰도를 넘지 않는다.
    """
    eligible = eligible_improved_video(scope)
    if eligible:
        confidence = Confidence.HIGH
        for evidence in eligible:
            confidence = min_confidence(confidence, evidence.confidence)
        return (
            ProgressLevel.VIDEO_VERIFIED_PROGRESS,
            [video_ref(evidence) for evidence in eligible],
            "외부 영상 분석이 명시된 이전 분석 대비 개선을 제시했다",
            confidence,
        )

    occurrences = result_occurrences(scope)
    distinct_times = {occurrence.reported_at for occurrence in occurrences}
    if len(occurrences) >= 2 and len(distinct_times) >= 2:
        return (
            ProgressLevel.RESULT_REPEATED,
            [occurrence.reference for occurrence in occurrences],
            "서로 다른 시점의 연습 결과 보고가 반복됐다. 영상 확인은 아직 없다",
            Confidence.MEDIUM,
        )

    reports = user_reported_progress_messages(scope)
    refs = [message_ref(message) for message in reports]
    refs.extend(occurrence.reference for occurrence in occurrences)
    if refs:
        return (
            ProgressLevel.USER_REPORTED_PROGRESS,
            refs,
            "사용자가 개선을 보고했다. 영상으로 확인된 변화는 아니다",
            Confidence.LOW,
        )
    return ProgressLevel.NONE, [], "발전 근거 없음", Confidence.LOW


# --------------------------------------------------------------------------
# Need signals
# --------------------------------------------------------------------------


def repeated_confirmation_evidence(scope: Scope) -> list[EvidenceReference]:
    """같은 방향을 반복 확인하는 신호. 불안이나 불신으로 해석하지 않는다."""
    refs = [
        behavior_ref(event)
        for event in scope.behavior_events
        if event.event_type is BehaviorEventType.TOPIC_REPEATED
    ]
    direction_messages = [
        message
        for message in scope.messages
        if message.role == "user"
        and detect_explicit_intent(message.text) is ExplicitIntent.DIRECTION_CONFIRMATION
    ]
    if len(direction_messages) >= 2:
        refs.extend(message_ref(message) for message in direction_messages)
    return refs


def difficulty_evidence(scope: Scope) -> list[EvidenceReference]:
    refs = [
        feedback_ref(event)
        for event in scope.feedback_events
        if event.feedback_type in (FeedbackType.HARD_TO_UNDERSTAND, FeedbackType.TOO_LONG)
    ]
    refs.extend(
        message_ref(message)
        for message in scope.messages
        if message.role == "user"
        and any(t in message.text for t in DIFFICULTY_TOKENS + LENGTH_COMPLAINT_TOKENS)
    )
    return refs


def actionable_evidence(scope: Scope) -> list[EvidenceReference]:
    return [
        message_ref(message)
        for message in scope.messages
        if message.role == "user" and any(t in message.text for t in ACTIONABLE_TOKENS)
    ]


def progress_recognition_evidence(scope: Scope) -> list[EvidenceReference]:
    """발전 인정 니즈의 근거. 발화뿐 아니라 결과 보고 이벤트·피드백도 포함한다."""
    refs = [message_ref(message) for message in user_reported_progress_messages(scope)]
    refs.extend(occurrence.reference for occurrence in result_occurrences(scope))
    return refs


def reframing_evidence(scope: Scope) -> list[EvidenceReference]:
    """사용자 느낌과 영상 관찰이 다를 때만 생성한다. 영상 관찰을 새로 만들지 않는다."""
    if not scope.video_evidence:
        return []
    refs = [video_ref(evidence) for evidence in scope.video_evidence]
    refs.append(message_ref(scope.latest_user_message))
    return refs


def current_turn_behavior_events(scope: Scope) -> list[BehaviorEvent]:
    """참여도에 쓸 수 있는 행동 이벤트.

    현재 활성 주제이면서 현재 turn 에 속한 것만 쓴다. 현재 turn 은 직전 사용자 메시지
    이후에 생긴 이벤트이거나 현재 사용자 메시지에 연결된 이벤트다.
    과거 어느 시점의 영상 업로드가 계속 참여도를 올리지 않게 한다.
    """
    latest = scope.latest_user_message
    previous = scope.previous_user_message
    boundary = previous.created_at if previous is not None else latest.created_at

    def in_current_turn(event: BehaviorEvent) -> bool:
        if event.related_message_id == latest.message_id:
            return True
        if previous is not None:
            return event.created_at > boundary
        return event.created_at >= boundary

    return [event for event in scope.behavior_events if in_current_turn(event)]


def is_correction_of_inference(text: str) -> bool:
    return any(token in text for token in CORRECTION_OF_INFERENCE_TOKENS)
