"""상태 추적 결과를 사람이 읽을 수 있는 짧은 문장으로 바꾸는 결정적 renderer.

외부 LLM 을 호출하지 않는다. 같은 상태면 항상 같은 문장이 나온다.
여기서 만드는 문장은 골프 코칭 답변이 아니라 "트래커가 무엇을 기록했는지"의 설명이다.
새로운 스윙 관찰이나 교정 방법을 만들어내지 않는다.
"""

from __future__ import annotations

from schemas import (
    ConversationState,
    ExplicitIntent,
    NeedType,
    ProgressLevel,
    ResponseStrategy,
)

DISCLAIMER = "이 답변은 상태 추적 POC 의 설명이며 골프 코칭 결과가 아닙니다."

_INTENT_PHRASE = {
    ExplicitIntent.CAUSE_EXPLANATION: "원인을 묻는 질문으로 기록했습니다.",
    ExplicitIntent.CORRECTION_ACTION: "교정 방법을 묻는 질문으로 기록했습니다.",
    ExplicitIntent.COMPARISON: "이전과 비교해달라는 요청으로 기록했습니다.",
    ExplicitIntent.DIRECTION_CONFIRMATION: "지금 방향이 맞는지 확인하는 질문으로 기록했습니다.",
    ExplicitIntent.PROGRESS_CHECK: "진행 상황을 확인하는 질문으로 기록했습니다.",
    ExplicitIntent.GENERAL_QUESTION: "일반 질문으로 기록했습니다.",
    ExplicitIntent.UNKNOWN: "이 문장만으로는 요청 목적을 확정하지 않았습니다.",
}

_PROGRESS_PHRASE = {
    ProgressLevel.USER_REPORTED_PROGRESS: (
        "이번에는 효과가 있었다고 기록했습니다. 아직 영상으로 확인한 변화는 아니므로, "
        "다음에도 같은 결과가 반복되는지 이어서 보겠습니다."
    ),
    ProgressLevel.RESULT_REPEATED: (
        "서로 다른 시점의 결과가 반복됐다고 기록했습니다. 아직 영상으로 확인한 변화는 아닙니다."
    ),
    ProgressLevel.VIDEO_VERIFIED_PROGRESS: (
        "외부 영상 분석이 이전 분석과 비교해 개선을 제시했습니다. "
        "여기서부터는 사용자 체감이 아니라 영상 근거로 기록합니다."
    ),
}

_NEED_PHRASE = {
    NeedType.NEEDS_SIMPLER_EXPLANATION: "설명이 어렵거나 길다는 신호를 받았습니다.",
    NeedType.NEEDS_CERTAINTY: (
        "같은 방향을 여러 번 확인하셨습니다. 불안이나 불신으로 판정하지는 않았습니다."
    ),
    NeedType.NEEDS_ACTIONABLE_STEP: "다음에 할 행동을 묻는 신호로 봤습니다.",
    NeedType.NEEDS_PROGRESS_RECOGNITION: "실행 결과 보고로 기록했습니다.",
    NeedType.NEEDS_PROBLEM_REFRAMING: (
        "말씀하신 원인과 영상 관찰의 초점이 다릅니다. 영상 관찰을 분석 근거로 먼저 씁니다."
    ),
}


def _need_lines(state: ConversationState) -> list[str]:
    lines: list[str] = []
    for need in state.inferred_needs:
        phrase = _NEED_PHRASE.get(need.need_type)
        if phrase:
            lines.append(phrase)
    return lines


def _open_loop_line(state: ConversationState) -> str | None:
    if not state.unresolved_open_loops:
        return None
    loop = state.unresolved_open_loops[0]
    return f"다음 확인 항목이 남아 있습니다: {loop.next_verification}"


def render_demo_reply(state: ConversationState) -> str:
    """상태에서 결정적으로 답변 문장을 만든다."""
    strategy = state.next_response_strategy
    lines: list[str] = []

    if strategy is ResponseStrategy.DO_NOT_INFER:
        lines.append("확인했어요.")
        lines.append("지금 입력만으로는 무엇이 필요한지, 만족했는지 판단하지 않았습니다.")

    elif strategy is ResponseStrategy.RECOGNIZE_MEANINGFUL_PROGRESS:
        phrase = _PROGRESS_PHRASE.get(state.progress.level)
        if phrase:
            lines.append(phrase)
        cap = state.progress.recognition_intensity_cap.value
        lines.append(f"인정 강도는 {cap} 까지만 허용했습니다.")

    elif strategy is ResponseStrategy.REDUCE_EXPLANATION_LENGTH:
        lines.append("설명이 길거나 어렵다는 신호를 받았습니다.")
        lines.append("다음 답변은 더 짧게 만들도록 기록했습니다.")

    elif strategy is ResponseStrategy.CONNECT_PREVIOUS_COACHING_TOPIC:
        lines.append("최근 반응이 평소보다 짧아졌습니다.")
        lines.append(
            "참여도 감소 가능성만 본 것이고 불만이나 이탈로 판정하지는 않았습니다. "
            "이전 코칭 주제와 연결해서 이어가겠습니다."
        )

    elif strategy is ResponseStrategy.ASK_ONE_CLARIFYING_QUESTION:
        lines.append("근거가 아직 한 가지뿐이라 확인 질문 하나가 필요하다고 봤습니다.")

    else:  # ANSWER_DIRECTLY
        lines.append(_INTENT_PHRASE[state.explicit_intent])
        if not state.confirmed_user_facts:
            lines.append("영상 근거가 없어 실제 스윙 원인은 확정하지 않았습니다.")

    lines.extend(_need_lines(state))

    if state.secondary_strategy is ResponseStrategy.OPEN_NEXT_PRACTICE_LOOP:
        lines.append("다음 연습 결과를 이어서 확인하겠습니다.")

    loop_line = _open_loop_line(state)
    if loop_line:
        lines.append(loop_line)

    topic = state.active_coaching_topic
    if topic is not None:
        lines.append(f"현재 코칭 주제: {topic.user_problem}")

    return "\n".join(lines)
