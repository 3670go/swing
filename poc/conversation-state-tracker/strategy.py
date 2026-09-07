"""응답 전략 선택.

우선순위 사다리에서 처음 맞는 하나만 주 전략이 된다. 보조 전략은 최대 하나다.
"""

from __future__ import annotations

from schemas import (
    CoachingTopicRef,
    EngagementState,
    EngagementTrend,
    ExplicitIntent,
    InferredNeed,
    NeedType,
    ProgressAssessment,
    ProgressLevel,
    ResponseStrategy,
)


def select_strategy(
    *,
    explicit_intent: ExplicitIntent,
    needs: list[InferredNeed],
    engagement: EngagementState,
    progress: ProgressAssessment,
    topic: CoachingTopicRef | None,
    has_any_evidence: bool,
) -> tuple[ResponseStrategy, ResponseStrategy | None]:
    """주 전략 하나와 선택적 보조 전략 하나를 돌려준다."""
    need_types = {need.need_type for need in needs}

    if progress.level is not ProgressLevel.NONE:
        # 사용자 보고 단계에서도 인정할 수 있다. 다만 인정 강도는
        # ProgressAssessment.recognition_intensity_cap 이 제한한다.
        return (
            ResponseStrategy.RECOGNIZE_MEANINGFUL_PROGRESS,
            ResponseStrategy.OPEN_NEXT_PRACTICE_LOOP,
        )

    if NeedType.NEEDS_SIMPLER_EXPLANATION in need_types:
        return ResponseStrategy.REDUCE_EXPLANATION_LENGTH, None

    if explicit_intent is not ExplicitIntent.UNKNOWN:
        secondary = None
        if (
            topic is not None
            and engagement.trend is EngagementTrend.DECREASING
            or NeedType.NEEDS_PROBLEM_REFRAMING in need_types
            and topic is not None
        ):
            secondary = ResponseStrategy.CONNECT_PREVIOUS_COACHING_TOPIC
        return ResponseStrategy.ANSWER_DIRECTLY, secondary

    if need_types - {NeedType.UNKNOWN}:
        return ResponseStrategy.ASK_ONE_CLARIFYING_QUESTION, None

    if engagement.trend is EngagementTrend.DECREASING:
        # 참여도 감소 가능성만 반영한다. 불만이나 이탈로 확정하지 않는다.
        if topic is not None:
            return ResponseStrategy.CONNECT_PREVIOUS_COACHING_TOPIC, None
        return ResponseStrategy.ASK_ONE_CLARIFYING_QUESTION, None

    if not has_any_evidence:
        return ResponseStrategy.DO_NOT_INFER, None

    return ResponseStrategy.DO_NOT_INFER, None
