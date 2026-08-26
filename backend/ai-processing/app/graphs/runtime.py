from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph

from app.conversation_policy import (
    ConversationPolicy,
    build_conversation_policy,
    enforce_conversation_policy,
)
from app.domain.analysis_policy import (
    AnalysisPolicyViolation,
    build_base_assessment,
    validate_frozen_assessment,
    validate_media_content,
    validate_observation,
)
from app.domain.models import (
    BaseAssessment,
    CoachContent,
    CoachReply,
    ConversationReply,
    ShotContext,
    VisionObservation,
)
from app.llm import ModelAdapter


class GraphContractError(RuntimeError):
    """A graph node produced output outside the golf analysis contract."""


class TextGraphState(TypedDict):
    message: str
    context: ShotContext
    history: list[dict[str, Any]]
    latest_analysis: dict[str, Any] | None
    policy: NotRequired[ConversationPolicy]
    content: NotRequired[CoachContent]
    reply: NotRequired[ConversationReply]
    interaction_meta: NotRequired[dict[str, Any]]


class AnalysisGraphState(TypedDict):
    frame_paths: list[Path]
    media_kind: Literal["photo", "video"]
    context: ShotContext
    question: str
    history: list[dict[str, Any]]
    observation: NotRequired[VisionObservation]
    base_assessment: NotRequired[BaseAssessment]
    policy: NotRequired[ConversationPolicy]
    content: NotRequired[CoachContent]
    conversation: NotRequired[ConversationReply]
    reply: NotRequired[CoachReply | None]
    interaction_meta: NotRequired[dict[str, Any]]
    status: NotRequired[Literal["succeeded", "limited", "rejected"]]


def _guard_observation(state: AnalysisGraphState) -> dict[str, VisionObservation]:
    observation = state["observation"]
    try:
        validate_observation(observation, state["media_kind"])
    except AnalysisPolicyViolation as error:
        raise GraphContractError(str(error)) from error
    return {"observation": observation}


def _route_observation(state: AnalysisGraphState) -> str:
    return "reject" if not state["observation"].is_golf_media else "assess"


def _reject_media(state: AnalysisGraphState) -> dict[str, Any]:
    return {"status": "rejected", "reply": None}


def _domain_assess(state: AnalysisGraphState) -> dict[str, BaseAssessment]:
    return {"base_assessment": build_base_assessment(state["observation"])}


def _freeze_base_assessment(state: AnalysisGraphState) -> dict[str, BaseAssessment]:
    assessment = state["base_assessment"]
    try:
        validate_frozen_assessment(assessment, state["observation"])
    except AnalysisPolicyViolation as error:
        raise GraphContractError(str(error)) from error
    return {"base_assessment": assessment}


def _guard_text_content(state: TextGraphState) -> dict[str, CoachContent]:
    content = state["content"]
    if content.evidence_mode != "text_only":
        raise GraphContractError("Text graph content claimed current media evidence")
    return {"content": content}


def _guard_media_content(state: AnalysisGraphState) -> dict[str, CoachContent]:
    content = state["content"]
    try:
        validate_media_content(
            content,
            media_kind=state["media_kind"],
            assessment=state["base_assessment"],
            observation_count=len(state["observation"].observations),
        )
    except AnalysisPolicyViolation as error:
        raise GraphContractError(str(error)) from error
    return {"content": content}


def build_text_content_graph(model: ModelAdapter):
    """Compile text coaching content without writing a user-facing message."""

    def apply_policy(state: TextGraphState) -> dict[str, ConversationPolicy]:
        policy = build_conversation_policy(
            message=state["message"],
            history=state["history"],
            latest_analysis=state["latest_analysis"],
        )
        return {"policy": policy}

    async def compose_content(state: TextGraphState) -> dict[str, CoachContent]:
        content = await model.compose_text_content(
            message=state["message"],
            context=state["context"],
            history=state["history"],
            latest_analysis=state["latest_analysis"],
            policy=state["policy"].prompt_payload(),
        )
        return {"content": content}

    builder = StateGraph(TextGraphState)
    builder.add_node("response_policy", apply_policy)
    builder.add_node("compose_content", compose_content)
    builder.add_node("content_guard", _guard_text_content)
    builder.add_edge(START, "response_policy")
    builder.add_edge("response_policy", "compose_content")
    builder.add_edge("compose_content", "content_guard")
    builder.add_edge("content_guard", END)
    return builder.compile()


def build_text_graph(model: ModelAdapter):
    """Generate coaching content, then write the user-facing message."""

    async def write_conversation(state: TextGraphState) -> dict[str, ConversationReply]:
        reply = await model.write_conversation(
            user_message=state["message"],
            history=state["history"],
            content=state["content"],
            policy=state["policy"].prompt_payload(),
        )
        return {"reply": reply}

    def guard_surface(state: TextGraphState) -> dict[str, Any]:
        reply, interaction_meta = enforce_conversation_policy(
            state["reply"],
            state["policy"],
            state["content"],
        )
        return {"reply": reply, "interaction_meta": interaction_meta}

    builder = StateGraph(TextGraphState)
    builder.add_node("content_pipeline", build_text_content_graph(model))
    builder.add_node("conversation_writer", write_conversation)
    builder.add_node("surface_guard", guard_surface)
    builder.add_edge(START, "content_pipeline")
    builder.add_edge("content_pipeline", "conversation_writer")
    builder.add_edge("conversation_writer", "surface_guard")
    builder.add_edge("surface_guard", END)
    return builder.compile()


def build_analysis_content_graph(model: ModelAdapter):
    """Freeze visual evidence and compose content without surface writing."""

    async def observe(state: AnalysisGraphState) -> dict[str, VisionObservation]:
        context = state["context"]
        observation = await model.observe(
            frame_paths=state["frame_paths"],
            media_kind=state["media_kind"],
            shot_profile=context.shot_profile,
            camera_view=context.camera_view,
            handedness=context.handedness,
        )
        return {"observation": observation}

    def apply_policy(state: AnalysisGraphState) -> dict[str, ConversationPolicy]:
        policy = build_conversation_policy(
            message=state["question"] or "전체 우선순위로 분석해줘",
            history=state["history"],
            latest_analysis=state["base_assessment"].model_dump(mode="json"),
        )
        return {"policy": policy}

    async def compose_content(state: AnalysisGraphState) -> dict[str, CoachContent]:
        content = await model.compose_media_content(
            observation=state["observation"],
            base_assessment=state["base_assessment"],
            context=state["context"],
            question=state["question"],
            media_kind=state["media_kind"],
            policy=state["policy"].prompt_payload(),
        )
        return {"content": content}

    def complete_content(
        state: AnalysisGraphState,
    ) -> dict[str, Literal["succeeded", "limited"]]:
        return {"status": "limited" if state["media_kind"] == "photo" else "succeeded"}

    builder = StateGraph(AnalysisGraphState)
    builder.add_node("vision_observe", observe)
    builder.add_node("observation_guard", _guard_observation)
    builder.add_node("reject_media", _reject_media)
    builder.add_node("domain_assess", _domain_assess)
    builder.add_node("freeze_base_assessment", _freeze_base_assessment)
    builder.add_node("response_policy", apply_policy)
    builder.add_node("compose_content", compose_content)
    builder.add_node("content_guard", _guard_media_content)
    builder.add_node("complete_content", complete_content)
    builder.add_edge(START, "vision_observe")
    builder.add_edge("vision_observe", "observation_guard")
    builder.add_conditional_edges(
        "observation_guard",
        _route_observation,
        {"reject": "reject_media", "assess": "domain_assess"},
    )
    builder.add_edge("reject_media", END)
    builder.add_edge("domain_assess", "freeze_base_assessment")
    builder.add_edge("freeze_base_assessment", "response_policy")
    builder.add_edge("response_policy", "compose_content")
    builder.add_edge("compose_content", "content_guard")
    builder.add_edge("content_guard", "complete_content")
    builder.add_edge("complete_content", END)
    return builder.compile()


def build_analysis_graph(model: ModelAdapter):
    """Generate frozen analysis content, then write the user-facing message."""

    def route_surface(state: AnalysisGraphState) -> str:
        return "reject" if state["status"] == "rejected" else "write"

    async def write_conversation(state: AnalysisGraphState) -> dict[str, ConversationReply]:
        conversation = await model.write_conversation(
            user_message=state["question"] or "스윙 전체를 봐줘",
            history=state["history"],
            content=state["content"],
            policy=state["policy"].prompt_payload(),
        )
        return {"conversation": conversation}

    def guard_surface(state: AnalysisGraphState) -> dict[str, Any]:
        conversation, interaction_meta = enforce_conversation_policy(
            state["conversation"],
            state["policy"],
            state["content"],
        )
        reply = CoachReply(
            base_assessment=state["base_assessment"],
            content=state["content"],
            conversation=conversation,
        )
        return {
            "conversation": conversation,
            "reply": reply,
            "interaction_meta": interaction_meta,
        }

    builder = StateGraph(AnalysisGraphState)
    builder.add_node("content_pipeline", build_analysis_content_graph(model))
    builder.add_node("conversation_writer", write_conversation)
    builder.add_node("surface_guard", guard_surface)
    builder.add_edge(START, "content_pipeline")
    builder.add_conditional_edges(
        "content_pipeline",
        route_surface,
        {"reject": END, "write": "conversation_writer"},
    )
    builder.add_edge("conversation_writer", "surface_guard")
    builder.add_edge("surface_guard", END)
    return builder.compile()
