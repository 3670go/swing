import re
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph

from app.domain.analysis_policy import (
    AnalysisPolicyViolation,
    build_base_assessment,
    validate_frozen_assessment,
    validate_observation,
)
from app.domain.models import (
    BaseAssessment,
    CoachContent,
    CoachingScope,
    CoachingTopicCandidate,
    CoachingTurnPlan,
    ContextPacket,
    UserContextFactCandidate,
    VisionObservation,
)
from app.graphs.coaching_guards import (
    CoachingGuardViolation,
    selected_shot_context_only,
    validate_media_turn_plan,
    validate_rejected_without_plan,
    validate_text_turn_plan,
)
from app.llm import GeneratedTextTurn, ModelAdapter


class GraphContractError(RuntimeError):
    """A graph node produced output outside the golf analysis contract."""


class TextGraphState(TypedDict):
    context_packet: ContextPacket
    turn_route: NotRequired[Literal["social", "coaching"]]
    coaching_turn_plan: NotRequired[CoachingTurnPlan]


class VisionObservationState(TypedDict):
    frame_paths: list[Path]
    media_kind: Literal["photo", "video"]
    shot_profile: str
    camera_view: str
    handedness: str
    observation: NotRequired[VisionObservation]


class AnalysisGraphState(TypedDict):
    frame_paths: list[Path]
    media_kind: Literal["photo", "video"]
    context_packet: ContextPacket
    observation: NotRequired[VisionObservation]
    base_assessment: NotRequired[BaseAssessment]
    coaching_turn_plan: NotRequired[CoachingTurnPlan]
    status: NotRequired[Literal["succeeded", "limited", "rejected"]]


# Legacy state aliases kept only for callers that import the names.
LegacyTextGraphState = TextGraphState
LegacyAnalysisGraphState = AnalysisGraphState


def _vision_observation_input(state: AnalysisGraphState) -> VisionObservationState:
    blind_context = selected_shot_context_only(state["context_packet"])
    return {
        "frame_paths": state["frame_paths"],
        "media_kind": state["media_kind"],
        "shot_profile": blind_context["shot_profile"],
        "camera_view": blind_context["camera_view"],
        "handedness": blind_context["handedness"],
    }


def _guard_observation(state: AnalysisGraphState) -> dict[str, VisionObservation]:
    observation = state["observation"]
    try:
        validate_observation(observation, state["media_kind"])
    except AnalysisPolicyViolation as error:
        raise GraphContractError(str(error)) from error
    return {"observation": observation}


def _route_observation(state: AnalysisGraphState) -> str:
    return "reject" if not state["observation"].is_golf_media else "assess"


def _reject_media(_state: AnalysisGraphState) -> dict[str, Any]:
    return {"status": "rejected"}


def _domain_assess(state: AnalysisGraphState) -> dict[str, BaseAssessment]:
    return {"base_assessment": build_base_assessment(state["observation"])}


def _freeze_base_assessment(state: AnalysisGraphState) -> dict[str, BaseAssessment]:
    assessment = state["base_assessment"]
    try:
        validate_frozen_assessment(assessment, state["observation"])
    except AnalysisPolicyViolation as error:
        raise GraphContractError(str(error)) from error
    return {"base_assessment": assessment}


def _guard_text_plan(state: TextGraphState) -> dict[str, CoachingTurnPlan]:
    plan = state["coaching_turn_plan"]
    try:
        validate_text_turn_plan(plan)
    except CoachingGuardViolation as error:
        raise GraphContractError(str(error)) from error
    return {"coaching_turn_plan": plan}


def _guard_media_plan(state: AnalysisGraphState) -> dict[str, CoachingTurnPlan]:
    plan = state["coaching_turn_plan"]
    try:
        validate_media_turn_plan(
            plan,
            media_kind=state["media_kind"],
            assessment=state["base_assessment"],
            observation=state["observation"],
        )
    except (AnalysisPolicyViolation, CoachingGuardViolation) as error:
        raise GraphContractError(str(error)) from error
    return {"coaching_turn_plan": plan}


def _guard_rejected_plan(state: AnalysisGraphState) -> dict[str, Any]:
    try:
        validate_rejected_without_plan(state["status"], state.get("coaching_turn_plan"))
    except CoachingGuardViolation as error:
        raise GraphContractError(str(error)) from error
    return {}


def build_text_turn_plan(
    generated: GeneratedTextTurn | CoachContent,
    context_packet: ContextPacket,
) -> CoachingTurnPlan:
    """Map a compact provider draft to candidate-only internal state."""
    if isinstance(generated, CoachContent):
        generated = GeneratedTextTurn(
            content=generated,
            coaching_problem=None,
            context_facts=(),
        )
    selected = context_packet.request_context.selected_shot_context
    current_scope = CoachingScope(
        shot_profile=selected.shot_profile,
        club=selected.club,
        club_group=None,
        short_game_type=selected.short_game_type,
    )
    topic_candidate = None
    if generated.coaching_problem and context_packet.active_coaching_topic is None:
        topic_candidate = CoachingTopicCandidate(
            action="CREATE_NEW",
            target_topic_id=None,
            expected_version=None,
            scope=current_scope,
            title=generated.coaching_problem,
        )
    fact_candidates = [
        UserContextFactCandidate(
            action=fact.action,
            fact_type=fact.fact_type,
            body_region=fact.body_region,
            statement=fact.statement,
            scope=current_scope if fact.use_current_shot_scope else None,
        )
        for fact in generated.context_facts
    ]
    return CoachingTurnPlan(
        coach_content=generated.content,
        problem_reframe_candidate=None,
        coaching_topic_candidate=topic_candidate,
        user_context_fact_candidates=fact_candidates,
        roadmap_update_candidates=[],
        progress_candidate=None,
        recognition_candidate=None,
        open_loop_candidate=None,
    )


def _wrap_media_coach_content(content: CoachContent) -> CoachingTurnPlan:
    """Build a valid plan locally after the provider returns compact media content."""
    return CoachingTurnPlan(
        coach_content=content,
        problem_reframe_candidate=None,
        coaching_topic_candidate=None,
        user_context_fact_candidates=[],
        roadmap_update_candidates=[],
        progress_candidate=None,
        recognition_candidate=None,
        open_loop_candidate=None,
    )


def _social_kind(message: str) -> Literal["greeting", "thanks", "laughter"] | None:
    normalized = re.sub(r"[\s!?.,~]+", "", message.casefold())
    if normalized in {"안녕", "안녕하세요", "하이", "하잉", "헬로", "hello", "hi", "ㅎㅇ"}:
        return "greeting"
    if normalized in {
        "고마워",
        "고마워요",
        "감사",
        "감사해",
        "감사합니다",
        "땡큐",
        "thanks",
        "thankyou",
    }:
        return "thanks"
    if re.fullmatch(r"[ㅋㅎ]{2,}", normalized):
        return "laughter"
    return None


def _classify_text_turn(state: TextGraphState) -> dict[str, Literal["social", "coaching"]]:
    message = state["context_packet"].request_context.user_message
    return {"turn_route": "social" if _social_kind(message) is not None else "coaching"}


def _route_text_turn(state: TextGraphState) -> Literal["social", "coaching"]:
    return state["turn_route"]


def _compose_social_plan(state: TextGraphState) -> dict[str, CoachingTurnPlan]:
    packet = state["context_packet"]
    kind = _social_kind(packet.request_context.user_message)
    topic = packet.active_coaching_topic

    if kind == "greeting":
        direct_answer = "안녕하세요."
        follow_up = (
            f"지난번에 보던 {topic.user_problem}부터 이어서 볼까요, "
            "아니면 오늘 달라진 점부터 볼까요?"
            if topic is not None
            else "오늘 가장 먼저 확인하고 싶은 스윙 문제는 뭐예요?"
        )
    elif kind == "thanks":
        direct_answer = "좋아요. 도움이 된 부분은 다음 스윙에서도 그대로 가져가면 됩니다."
        follow_up = "다음 스윙에서 무엇이 달라졌는지 이어서 알려줄래요?"
    else:
        direct_answer = "ㅎㅎ 편하게 말해도 돼요."
        follow_up = "방금 설명에서 걸리는 부분이 있었어요?"

    content = CoachContent(
        evidence_mode="text_only",
        direct_answer=direct_answer,
        causal_chain=[],
        evidence_boundary="소셜 응답이며 현재 스윙 판정을 포함하지 않습니다.",
        cannot_determine=[],
        observation_indexes=[],
        follow_up_information_needed=follow_up,
    )
    return {
        "coaching_turn_plan": CoachingTurnPlan(
            coach_content=content,
            problem_reframe_candidate=None,
            coaching_topic_candidate=None,
            user_context_fact_candidates=[],
            roadmap_update_candidates=[],
            progress_candidate=None,
            recognition_candidate=None,
            open_loop_candidate=None,
        )
    }


def build_text_content_graph(model: ModelAdapter):
    """Route high-confidence social turns before model-backed golf coaching."""

    async def compose_coaching_plan(state: TextGraphState) -> dict[str, CoachingTurnPlan]:
        generated = await model.compose_text_coach_content(
            context_packet=state["context_packet"],
        )
        return {
            "coaching_turn_plan": build_text_turn_plan(
                generated,
                state["context_packet"],
            )
        }

    builder = StateGraph(TextGraphState)
    builder.add_node("classify_turn", _classify_text_turn)
    builder.add_node("compose_social_plan", _compose_social_plan)
    builder.add_node("compose_coaching_plan", compose_coaching_plan)
    builder.add_node("plan_guard", _guard_text_plan)
    builder.add_edge(START, "classify_turn")
    builder.add_conditional_edges(
        "classify_turn",
        _route_text_turn,
        {"social": "compose_social_plan", "coaching": "compose_coaching_plan"},
    )
    builder.add_edge("compose_social_plan", "plan_guard")
    builder.add_edge("compose_coaching_plan", "plan_guard")
    builder.add_edge("plan_guard", END)
    return builder.compile()


def build_blind_observation_graph(model: ModelAdapter):
    """Compile visual observation with a state that cannot carry user context."""

    async def observe(state: VisionObservationState) -> dict[str, VisionObservation]:
        observation = await model.observe(
            frame_paths=state["frame_paths"],
            media_kind=state["media_kind"],
            shot_profile=state["shot_profile"],
            camera_view=state["camera_view"],
            handedness=state["handedness"],
        )
        return {"observation": observation}

    builder = StateGraph(VisionObservationState)
    builder.add_node("vision_observe", observe)
    builder.add_edge(START, "vision_observe")
    builder.add_edge("vision_observe", END)
    return builder.compile()


def build_analysis_content_graph(model: ModelAdapter):
    """Freeze visual evidence before allowing ContextPacket comparison."""

    blind_observation_graph = build_blind_observation_graph(model)

    async def observe_blind(state: AnalysisGraphState) -> dict[str, VisionObservation]:
        result = await blind_observation_graph.ainvoke(
            _vision_observation_input(state),
        )
        return {"observation": result["observation"]}

    async def compose_plan(state: AnalysisGraphState) -> dict[str, CoachingTurnPlan]:
        packet = state["context_packet"]
        content = await model.compose_media_content(
            observation=state["observation"],
            base_assessment=state["base_assessment"],
            context=packet.request_context.selected_shot_context,
            question=packet.request_context.user_message,
            media_kind=state["media_kind"],
            policy={
                "analysis_goal": packet.request_context.selected_shot_context.analysis_goal,
                "answer_scope": "one_primary_finding",
            },
        )
        return {"coaching_turn_plan": _wrap_media_coach_content(content)}

    def complete_content(
        state: AnalysisGraphState,
    ) -> dict[str, Literal["succeeded", "limited"]]:
        return {"status": "limited" if state["media_kind"] == "photo" else "succeeded"}

    builder = StateGraph(AnalysisGraphState)
    builder.add_node("vision_observe", observe_blind)
    builder.add_node("observation_guard", _guard_observation)
    builder.add_node("reject_media", _reject_media)
    builder.add_node("reject_guard", _guard_rejected_plan)
    builder.add_node("domain_assess", _domain_assess)
    builder.add_node("freeze_base_assessment", _freeze_base_assessment)
    builder.add_node("compose_turn_plan", compose_plan)
    builder.add_node("plan_guard", _guard_media_plan)
    builder.add_node("complete_content", complete_content)
    builder.add_edge(START, "vision_observe")
    builder.add_edge("vision_observe", "observation_guard")
    builder.add_conditional_edges(
        "observation_guard",
        _route_observation,
        {"reject": "reject_media", "assess": "domain_assess"},
    )
    builder.add_edge("reject_media", "reject_guard")
    builder.add_edge("reject_guard", END)
    builder.add_edge("domain_assess", "freeze_base_assessment")
    builder.add_edge("freeze_base_assessment", "compose_turn_plan")
    builder.add_edge("compose_turn_plan", "plan_guard")
    builder.add_edge("plan_guard", "complete_content")
    builder.add_edge("complete_content", END)
    return builder.compile()
