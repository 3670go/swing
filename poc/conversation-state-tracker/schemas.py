"""Input and output schemas for the conversation state tracker POC.

원본 메시지(Message)와 파생 상태(ConversationState)를 분리한다.
모든 추정은 Inference 를 상속해 confidence / evidence / reason / last_updated_at 을 갖는다.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    """운영 app.domain.models.StrictModel 과 같은 정책. 코드 의존은 없다."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------


class EvidenceSourceType(StrEnum):
    """근거 출처.

    운영 계약(internal-api.openapi.yaml 2.0.0) EvidenceReference.source_type 매핑:
      MESSAGE        -> MESSAGE
      VIDEO_ANALYSIS -> ANALYSIS_EPISODE
      BEHAVIOR_EVENT -> 대응 값 없음 (POC 전용 확장)
      FEEDBACK_EVENT -> 대응 값 없음 (POC 전용 확장)
    """

    MESSAGE = "MESSAGE"
    BEHAVIOR_EVENT = "BEHAVIOR_EVENT"
    FEEDBACK_EVENT = "FEEDBACK_EVENT"
    VIDEO_ANALYSIS = "VIDEO_ANALYSIS"


class Confidence(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


CONFIDENCE_ORDER: dict[Confidence, int] = {
    Confidence.LOW: 0,
    Confidence.MEDIUM: 1,
    Confidence.HIGH: 2,
}


def min_confidence(left: Confidence, right: Confidence) -> Confidence:
    return left if CONFIDENCE_ORDER[left] <= CONFIDENCE_ORDER[right] else right


class BehaviorEventType(StrEnum):
    VIDEO_UPLOADED = "VIDEO_UPLOADED"
    RETURNED_TO_CONVERSATION = "RETURNED_TO_CONVERSATION"
    PRACTICE_RESULT_REPORTED = "PRACTICE_RESULT_REPORTED"
    FOLLOW_UP_QUESTION = "FOLLOW_UP_QUESTION"
    TOPIC_REPEATED = "TOPIC_REPEATED"


class FeedbackType(StrEnum):
    """지시서 4.3 의 9종.

    ACTUALLY_IMPROVED 만 결과 보고이고 나머지는 답변에 대한 신호다.
    """

    HELPFUL = "HELPFUL"
    HARD_TO_UNDERSTAND = "HARD_TO_UNDERSTAND"
    NOT_MY_PROBLEM = "NOT_MY_PROBLEM"
    PINPOINTED_PROBLEM = "PINPOINTED_PROBLEM"
    EASY_TO_UNDERSTAND = "EASY_TO_UNDERSTAND"
    IMMEDIATELY_ACTIONABLE = "IMMEDIATELY_ACTIONABLE"
    ACTUALLY_IMPROVED = "ACTUALLY_IMPROVED"
    TOO_LONG = "TOO_LONG"
    ANALYSIS_WRONG = "ANALYSIS_WRONG"


OUTCOME_REPORTING_FEEDBACK: frozenset[FeedbackType] = frozenset({FeedbackType.ACTUALLY_IMPROVED})
"""실제 행동 결과를 보고하는 피드백. 단순 신호 피드백과 증거 강도를 구분한다."""


class ExplicitIntent(StrEnum):
    CAUSE_EXPLANATION = "CAUSE_EXPLANATION"
    CORRECTION_ACTION = "CORRECTION_ACTION"
    COMPARISON = "COMPARISON"
    DIRECTION_CONFIRMATION = "DIRECTION_CONFIRMATION"
    PROGRESS_CHECK = "PROGRESS_CHECK"
    GENERAL_QUESTION = "GENERAL_QUESTION"
    UNKNOWN = "UNKNOWN"


class NeedType(StrEnum):
    NEEDS_CERTAINTY = "NEEDS_CERTAINTY"
    NEEDS_SIMPLER_EXPLANATION = "NEEDS_SIMPLER_EXPLANATION"
    NEEDS_ACTIONABLE_STEP = "NEEDS_ACTIONABLE_STEP"
    NEEDS_PROGRESS_RECOGNITION = "NEEDS_PROGRESS_RECOGNITION"
    NEEDS_PROBLEM_REFRAMING = "NEEDS_PROBLEM_REFRAMING"
    UNKNOWN = "UNKNOWN"


class EngagementLevel(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class EngagementTrend(StrEnum):
    INCREASING = "INCREASING"
    STABLE = "STABLE"
    DECREASING = "DECREASING"
    UNKNOWN = "UNKNOWN"


class ProgressLevel(StrEnum):
    """계약 §3.9 근거 수준. MILESTONE_COMPLETED 는 milestone 입력이 없어 POC 범위 밖."""

    NONE = "NONE"
    USER_REPORTED_PROGRESS = "USER_REPORTED_PROGRESS"
    RESULT_REPEATED = "RESULT_REPEATED"
    VIDEO_VERIFIED_PROGRESS = "VIDEO_VERIFIED_PROGRESS"


class RecognitionIntensity(StrEnum):
    """계약 §3.8 인정 강도."""

    NONE = "NONE"
    ACKNOWLEDGEMENT = "ACKNOWLEDGEMENT"
    SPECIFIC_RECOGNITION = "SPECIFIC_RECOGNITION"
    PROGRESS_DECLARATION = "PROGRESS_DECLARATION"


class ResponseStrategy(StrEnum):
    ANSWER_DIRECTLY = "ANSWER_DIRECTLY"
    ASK_ONE_CLARIFYING_QUESTION = "ASK_ONE_CLARIFYING_QUESTION"
    REDUCE_EXPLANATION_LENGTH = "REDUCE_EXPLANATION_LENGTH"
    CONNECT_PREVIOUS_COACHING_TOPIC = "CONNECT_PREVIOUS_COACHING_TOPIC"
    RECOGNIZE_MEANINGFUL_PROGRESS = "RECOGNIZE_MEANINGFUL_PROGRESS"
    OPEN_NEXT_PRACTICE_LOOP = "OPEN_NEXT_PRACTICE_LOOP"
    DO_NOT_INFER = "DO_NOT_INFER"


class VideoComparison(StrEnum):
    """영상 비교 판정. 대화 엔진이 생성하지 않고 외부 입력으로만 받는다."""

    IMPROVED = "IMPROVED"
    UNCHANGED = "UNCHANGED"
    REGRESSED = "REGRESSED"
    NOT_COMPARED = "NOT_COMPARED"


class OpenLoopState(StrEnum):
    """계약 §9.6 OpenLoop 상태."""

    PENDING = "PENDING"
    FULFILLED = "FULFILLED"
    REPLACED = "REPLACED"
    CANCELLED = "CANCELLED"


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class TrackerError(Exception):
    """POC 트래커의 결정적 실패 경로 최상위."""


class InputIntegrityError(TrackerError):
    """입력 payload 자체가 성립하지 않는다."""


class DuplicateIdError(InputIntegrityError):
    """같은 source type 안에서 ID 가 중복됐다."""


class DanglingReferenceError(InputIntegrityError):
    """입력에 존재하지 않는 ID 를 참조했다."""


class PriorStateConflictError(InputIntegrityError):
    """이전 상태가 현재 대화·주제와 충돌한다."""


class InferenceWithoutEvidenceError(TrackerError):
    """근거 없는 추정을 만들려 했다."""


class VideoEvidenceMutationError(TrackerError):
    """대화 엔진이 영상 근거를 수정하거나 새 관찰을 만들어냈다."""


# --------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------


class EvidenceReference(StrictModel):
    """메시지, 행동 이벤트, 피드백, 영상 분석을 동일한 형태로 참조한다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_type: EvidenceSourceType
    source_id: str = Field(min_length=1, max_length=80)


# --------------------------------------------------------------------------
# Input
# --------------------------------------------------------------------------


class Message(StrictModel):
    """원본 대화. 트래커는 이 값을 변경하지 않는다."""

    message_id: str = Field(min_length=1, max_length=80)
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=4000)
    created_at: datetime
    topic_id: str | None = Field(default=None, max_length=80)


class BehaviorEvent(StrictModel):
    event_id: str = Field(min_length=1, max_length=80)
    event_type: BehaviorEventType
    related_message_id: str | None = Field(default=None, max_length=80)
    created_at: datetime
    topic_id: str | None = Field(default=None, max_length=80)
    open_loop_id: str | None = Field(default=None, max_length=80)


class FeedbackEvent(StrictModel):
    feedback_id: str = Field(min_length=1, max_length=80)
    target_message_id: str = Field(min_length=1, max_length=80)
    feedback_type: FeedbackType
    reason: str | None = Field(default=None, max_length=500)
    created_at: datetime
    topic_id: str | None = Field(default=None, max_length=80)


class VideoAnalysisEvidence(StrictModel):
    """외부 영상 분석 모듈의 출력. 대화 모듈은 읽기만 한다.

    comparison 과 compared_to_analysis_id 는 POC 확장이다. 영상 개선 판정을
    대화 엔진이 만들어내지 않고 외부 입력으로만 받기 위해 필요하다.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    analysis_id: str = Field(min_length=1, max_length=80)
    observations: tuple[str, ...] = Field(min_length=1)
    confidence: Confidence
    source_frame_ids: tuple[str, ...] = ()
    comparison: VideoComparison = VideoComparison.NOT_COMPARED
    compared_to_analysis_id: str | None = Field(default=None, max_length=80)


class CoachingTopicRef(StrictModel):
    topic_id: str = Field(min_length=1, max_length=80)
    user_problem: str = Field(min_length=1, max_length=300)
    root_problem: str | None = Field(default=None, max_length=300)


class OpenLoopRef(StrictModel):
    open_loop_id: str = Field(min_length=1, max_length=80)
    topic_id: str | None = Field(default=None, max_length=80)
    next_verification: str = Field(min_length=1, max_length=500)
    state: OpenLoopState = OpenLoopState.PENDING
    created_at: datetime


class ConversationInput(StrictModel):
    user_id: str = Field(min_length=1, max_length=80)
    conversation_id: str = Field(min_length=1, max_length=80)
    messages: list[Message] = Field(min_length=1)
    behavior_events: list[BehaviorEvent] = Field(default_factory=list)
    feedback_events: list[FeedbackEvent] = Field(default_factory=list)
    video_evidence: list[VideoAnalysisEvidence] = Field(default_factory=list)
    active_coaching_topic: CoachingTopicRef | None = None
    open_loops: list[OpenLoopRef] = Field(default_factory=list)
    prior_state: ConversationState | None = None

    @field_validator("messages")
    @classmethod
    def _require_user_message(cls, value: list[Message]) -> list[Message]:
        if not any(message.role == "user" for message in value):
            raise ValueError("messages must contain at least one user message")
        return value


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicated: list[str] = []
    for value in values:
        if value in seen and value not in duplicated:
            duplicated.append(value)
        seen.add(value)
    return duplicated


def validate_input_integrity(payload: ConversationInput) -> None:
    """입력 ID 무결성을 검사한다.

    근거 종류가 다르면 같은 문자열 ID 를 써도 된다. 중복 검사는 source type 별로 한다.
    """
    groups = {
        "Message.message_id": [m.message_id for m in payload.messages],
        "BehaviorEvent.event_id": [e.event_id for e in payload.behavior_events],
        "FeedbackEvent.feedback_id": [e.feedback_id for e in payload.feedback_events],
        "VideoAnalysisEvidence.analysis_id": [v.analysis_id for v in payload.video_evidence],
        "OpenLoopRef.open_loop_id": [loop.open_loop_id for loop in payload.open_loops],
    }
    for label, values in groups.items():
        duplicated = _duplicates(values)
        if duplicated:
            raise DuplicateIdError(f"{label} 중복: {', '.join(duplicated)}")

    messages_by_id = {m.message_id: m for m in payload.messages}
    loop_ids = {loop.open_loop_id for loop in payload.open_loops}
    analysis_ids = {v.analysis_id for v in payload.video_evidence}

    for event in payload.behavior_events:
        if event.related_message_id is not None and event.related_message_id not in messages_by_id:
            raise DanglingReferenceError(
                f"BehaviorEvent {event.event_id}.related_message_id "
                f"가 존재하지 않는 메시지를 참조한다: {event.related_message_id}"
            )
        if event.open_loop_id is not None and event.open_loop_id not in loop_ids:
            raise DanglingReferenceError(
                f"BehaviorEvent {event.event_id}.open_loop_id "
                f"가 존재하지 않는 Open Loop 를 참조한다: {event.open_loop_id}"
            )

    for feedback in payload.feedback_events:
        target = messages_by_id.get(feedback.target_message_id)
        if target is None:
            raise DanglingReferenceError(
                f"FeedbackEvent {feedback.feedback_id}.target_message_id "
                f"가 존재하지 않는 메시지를 참조한다: {feedback.target_message_id}"
            )
        if target.role != "assistant":
            raise DanglingReferenceError(
                f"FeedbackEvent {feedback.feedback_id}.target_message_id "
                f"는 assistant 메시지를 참조해야 한다: {feedback.target_message_id}"
            )

    for evidence in payload.video_evidence:
        compared = evidence.compared_to_analysis_id
        if compared is None:
            continue
        if compared == evidence.analysis_id:
            raise DanglingReferenceError(
                f"VideoAnalysisEvidence {evidence.analysis_id} 가 자기 자신을 비교 대상으로 삼았다"
            )
        if compared not in analysis_ids:
            raise DanglingReferenceError(
                f"VideoAnalysisEvidence {evidence.analysis_id}.compared_to_analysis_id "
                f"가 존재하지 않는 분석을 참조한다: {compared}"
            )

    prior = payload.prior_state
    if prior is not None:
        current_topic = payload.active_coaching_topic
        prior_topic = prior.active_coaching_topic
        conflicting = current_topic is not None and prior_topic is not None
        if conflicting and current_topic.topic_id != prior_topic.topic_id:
            raise PriorStateConflictError(
                "prior_state 의 활성 주제가 현재 활성 주제와 다르다: "
                f"{prior_topic.topic_id} != {current_topic.topic_id}"
            )


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


class Inference(StrictModel):
    """모든 추정의 공통 계약. 근거가 없으면 존재할 수 없다."""

    confidence: Confidence
    evidence: list[EvidenceReference] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=300)
    last_updated_at: datetime


class InferredNeed(Inference):
    need_type: NeedType


class EngagementState(Inference):
    level: EngagementLevel
    trend: EngagementTrend


class ProgressAssessment(Inference):
    """사용자 보고 발전과 영상 확인 발전을 구분해서 보관한다."""

    level: ProgressLevel
    swing_improvement_confirmed: bool
    recognition_intensity_cap: RecognitionIntensity


class ConfirmedFact(StrictModel):
    """사용자가 직접 말했거나 영상에서 확인된 것만. 요약이나 재작성은 하지 않는다."""

    statement: str = Field(min_length=1, max_length=4000)
    source: EvidenceReference
    evidence_level: Literal["USER_REPORTED", "VIDEO_OBSERVED"]


class StyleBaseline(StrictModel):
    """표본이 부족하면 이 객체를 만들지 않는다(None)."""

    sample_size: int = Field(ge=1)
    average_message_length: float = Field(ge=0)
    frequent_acknowledgements: list[str]
    polite_form_ratio: float = Field(ge=0, le=1)
    question_ratio: float = Field(ge=0, le=1)
    elaboration_ratio: float = Field(ge=0, le=1)
    video_upload_count: int = Field(ge=0)
    practice_report_count: int = Field(ge=0)
    profanity_ratio: float = Field(ge=0, le=1)


class InferenceRevision(StrictModel):
    """이전 추정은 지우지 않고 변경 이력으로 남긴다.

    previous_inference 와 new_inference 중 최소 하나는 존재한다.
    trigger_evidence 는 실제로 변경을 일으킨 근거이며, 최신 사용자 메시지를 무조건 쓰지 않는다.
    """

    previous_inference: InferredNeed | None = None
    new_inference: InferredNeed | None = None
    trigger_evidence: list[EvidenceReference] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=300)
    revised_at: datetime

    @field_validator("new_inference")
    @classmethod
    def _require_one_side(cls, value: InferredNeed | None, info) -> InferredNeed | None:
        if value is None and info.data.get("previous_inference") is None:
            raise ValueError("previous_inference 와 new_inference 가 모두 비어 있다")
        return value


class ConversationState(StrictModel):
    explicit_intent: ExplicitIntent
    active_coaching_topic: CoachingTopicRef | None
    confirmed_user_facts: list[ConfirmedFact]
    style_baseline: StyleBaseline | None
    inferred_needs: list[InferredNeed]
    engagement_state: EngagementState
    progress: ProgressAssessment
    open_loops: list[OpenLoopRef]
    unresolved_open_loops: list[OpenLoopRef]
    next_response_strategy: ResponseStrategy
    secondary_strategy: ResponseStrategy | None
    selected_context_message_ids: list[str]
    inference_history: list[InferenceRevision]


ConversationInput.model_rebuild()
