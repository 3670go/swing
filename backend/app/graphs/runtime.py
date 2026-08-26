import hashlib
import json
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph

from app.conversation_policy import (
    ConversationPolicy,
    build_conversation_policy,
    enforce_conversation_policy,
)
from app.llm import ModelAdapter
from app.schemas import (
    AssessmentCategory,
    AssessmentFinding,
    BaseAssessment,
    CoachContent,
    CoachReply,
    ConversationReply,
    ShotContext,
    VisionObservation,
)

FORBIDDEN_MEASUREMENT_TERMS = (
    "club path",
    "face angle",
    "face-to-path",
    "attack angle",
    "low point",
    "ground reaction force",
    "클럽 패스",
    "페이스 앵글",
    "어택 앵글",
    "로우 포인트",
    "지면반력",
    "°",
)
CATEGORY_PRIORITY: dict[AssessmentCategory, int] = {
    "impact_structure": 1,
    "transition_sequence": 2,
    "arm_body_space": 3,
    "center_posture": 4,
    "backswing": 5,
    "tempo_shape": 6,
}
PHOTO_UNSUPPORTED_CATEGORIES = frozenset({"transition_sequence", "tempo_shape"})


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
    combined = " ".join(item.state for item in observation.observations).lower()
    forbidden = [term for term in FORBIDDEN_MEASUREMENT_TERMS if term in combined]
    if forbidden:
        raise GraphContractError(
            f"2D observation contains forbidden measurement claims: {', '.join(forbidden)}"
        )
    if state["media_kind"] == "photo":
        if len(observation.observations) > 4:
            raise GraphContractError("Photo observation exceeded the single-frame evidence limit")
        unsupported = {
            item.assessment_category
            for item in observation.observations
            if item.assessment_category in PHOTO_UNSUPPORTED_CATEGORIES
        }
        if unsupported:
            raise GraphContractError(
                "Photo observation claimed sequence-only categories: "
                + ", ".join(sorted(unsupported))
            )
    return {"observation": observation}


def _route_observation(state: AnalysisGraphState) -> str:
    return "reject" if not state["observation"].is_golf_media else "assess"


def _reject_media(state: AnalysisGraphState) -> dict[str, Any]:
    return {"status": "rejected", "reply": None}


def _importance_for(category: AssessmentCategory) -> Literal["high", "medium", "low"]:
    priority = CATEGORY_PRIORITY[category]
    if priority <= 2:
        return "high"
    if priority <= 4:
        return "medium"
    return "low"


def build_base_assessment(observation: VisionObservation) -> BaseAssessment:
    """Create the same base assessment for the same blind visual evidence."""
    grouped: dict[AssessmentCategory, list[tuple[int, str, float]]] = {}
    for index, item in enumerate(observation.observations):
        grouped.setdefault(item.assessment_category, []).append(
            (index, item.state, item.confidence)
        )

    ordered_categories = sorted(grouped, key=CATEGORY_PRIORITY.__getitem__)
    findings = [
        AssessmentFinding(
            category=category,
            observation_indexes=[item[0] for item in grouped[category]],
            summary=" ".join(item[1] for item in grouped[category]),
            confidence=sum(item[2] for item in grouped[category]) / len(grouped[category]),
        )
        for category in ordered_categories
    ]
    primary_category = ordered_categories[0]
    payload = {
        "primary_category": primary_category,
        "importance": _importance_for(primary_category),
        "findings": [finding.model_dump(mode="json") for finding in findings],
        "cannot_determine": observation.cannot_determine,
    }
    assessment_hash = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return BaseAssessment(**payload, assessment_hash=assessment_hash)


def _domain_assess(state: AnalysisGraphState) -> dict[str, BaseAssessment]:
    return {"base_assessment": build_base_assessment(state["observation"])}


def _freeze_base_assessment(state: AnalysisGraphState) -> dict[str, BaseAssessment]:
    assessment = state["base_assessment"]
    expected = build_base_assessment(state["observation"])
    if assessment.assessment_hash != expected.assessment_hash:
        raise GraphContractError("Base assessment changed before the freeze boundary")
    return {"base_assessment": assessment}


def _guard_text_content(state: TextGraphState) -> dict[str, CoachContent]:
    content = state["content"]
    if content.evidence_mode != "text_only":
        raise GraphContractError("Text graph content claimed current media evidence")
    return {"content": content}


def _guard_media_content(state: AnalysisGraphState) -> dict[str, CoachContent]:
    content = state["content"]
    expected_mode = "photo_limited" if state["media_kind"] == "photo" else "video_ready"
    if content.evidence_mode != expected_mode:
        raise GraphContractError("Media content used the wrong evidence mode")
    if content.base_assessment_hash != state["base_assessment"].assessment_hash:
        raise GraphContractError("Media content changed the frozen base assessment")
    observation_count = len(state["observation"].observations)
    if any(index < 0 or index >= observation_count for index in content.observation_indexes):
        raise GraphContractError("Media content referenced a missing observation")
    if state["media_kind"] == "photo":
        boundary = " ".join([content.evidence_boundary, *content.cannot_determine]).lower()
        if not any(term in boundary for term in ("동작 순서", "템포", "전환")):
            raise GraphContractError("Photo content omitted the motion-sequence evidence limit")
    return {"content": content}


def build_text_graph(model: ModelAdapter):
    """Compile content generation and surface writing as separate graph stages."""

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
    builder.add_node("response_policy", apply_policy)
    builder.add_node("compose_content", compose_content)
    builder.add_node("content_guard", _guard_text_content)
    builder.add_node("conversation_writer", write_conversation)
    builder.add_node("surface_guard", guard_surface)
    builder.add_edge(START, "response_policy")
    builder.add_edge("response_policy", "compose_content")
    builder.add_edge("compose_content", "content_guard")
    builder.add_edge("content_guard", "conversation_writer")
    builder.add_edge("conversation_writer", "surface_guard")
    builder.add_edge("surface_guard", END)
    return builder.compile()


def build_analysis_graph(model: ModelAdapter):
    """Freeze question-blind visual assessment before coaching composition."""

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
        status = "limited" if state["media_kind"] == "photo" else "succeeded"
        return {
            "conversation": conversation,
            "reply": reply,
            "status": status,
            "interaction_meta": interaction_meta,
        }

    builder = StateGraph(AnalysisGraphState)
    builder.add_node("vision_observe", observe)
    builder.add_node("observation_guard", _guard_observation)
    builder.add_node("reject_media", _reject_media)
    builder.add_node("domain_assess", _domain_assess)
    builder.add_node("freeze_base_assessment", _freeze_base_assessment)
    builder.add_node("response_policy", apply_policy)
    builder.add_node("compose_content", compose_content)
    builder.add_node("content_guard", _guard_media_content)
    builder.add_node("conversation_writer", write_conversation)
    builder.add_node("surface_guard", guard_surface)
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
    builder.add_edge("content_guard", "conversation_writer")
    builder.add_edge("conversation_writer", "surface_guard")
    builder.add_edge("surface_guard", END)
    return builder.compile()
