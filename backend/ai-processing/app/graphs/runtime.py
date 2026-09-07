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
    CoachingTurnPlan,
    ContextPacket,
    VisionObservation,
)
from app.graphs.coaching_guards import (
    CoachingGuardViolation,
    selected_shot_context_only,
    validate_media_turn_plan,
    validate_rejected_without_plan,
    validate_text_turn_plan,
)
from app.llm import ModelAdapter


class GraphContractError(RuntimeError):
    """A graph node produced output outside the golf analysis contract."""


class TextGraphState(TypedDict):
    context_packet: ContextPacket
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


def _wrap_text_coach_content(content: CoachContent) -> CoachingTurnPlan:
    """Deterministically wrap a text-only CoachContent into a CoachingTurnPlan.

    The text vertical slice generates only CoachContent from the provider; Python owns
    the empty state candidates so no coaching state is proposed from a text turn.
    """
    return CoachingTurnPlan(
        coach_content=content,
        problem_reframe_candidate=None,
        coaching_topic_candidate=None,
        roadmap_update_candidates=[],
        progress_candidate=None,
        recognition_candidate=None,
        open_loop_candidate=None,
    )


def build_text_content_graph(model: ModelAdapter):
    """Compile text coaching as one small CoachContent call wrapped into a plan."""

    async def compose_plan(state: TextGraphState) -> dict[str, CoachingTurnPlan]:
        content = await model.compose_text_coach_content(
            context_packet=state["context_packet"],
        )
        return {"coaching_turn_plan": _wrap_text_coach_content(content)}

    builder = StateGraph(TextGraphState)
    builder.add_node("compose_turn_plan", compose_plan)
    builder.add_node("plan_guard", _guard_text_plan)
    builder.add_edge(START, "compose_turn_plan")
    builder.add_edge("compose_turn_plan", "plan_guard")
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
        plan = await model.compose_coaching_turn_plan(
            context_packet=state["context_packet"],
            observation=state["observation"],
            base_assessment=state["base_assessment"],
            media_kind=state["media_kind"],
        )
        return {"coaching_turn_plan": plan}

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
