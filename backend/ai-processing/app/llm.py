import asyncio
import json
import logging
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import Settings
from app.domain.models import (
    BaseAssessment,
    CoachContent,
    CoachingTurnPlan,
    ContextPacket,
    ShotContext,
    UserContextFactType,
    VisionObservation,
)

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)
MODEL_MAX_ATTEMPTS = 2
RETRYABLE_MODEL_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
logger = logging.getLogger(__name__)


class UserContextFactDraft(BaseModel):
    """Only information the user explicitly stated in the current message."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["UPSERT", "REMOVE"]
    fact_type: UserContextFactType
    body_region: str | None = Field(default=None, max_length=64)
    statement: str = Field(min_length=1, max_length=500)
    use_current_shot_scope: bool = False


class TextCoachDraft(BaseModel):
    """Small provider-facing schema for a text-only coaching reply.

    Evidence claims and internal contract fields are intentionally excluded. The
    application supplies those fields deterministically after provider parsing.
    """

    model_config = ConfigDict(extra="forbid")

    direct_answer: str = Field(min_length=1, max_length=700)
    causal_chain: list[str] = Field(default_factory=list, max_length=3)
    cannot_determine: list[str] = Field(default_factory=list, max_length=8)
    single_change: str | None = Field(default=None, max_length=500)
    verification: str | None = Field(default=None, max_length=500)
    follow_up_question: str | None = Field(default=None, max_length=180)
    coaching_problem: str | None = Field(default=None, max_length=200)
    context_facts: list[UserContextFactDraft] = Field(default_factory=list, max_length=4)


class ConversationDraft(BaseModel):
    """One natural user-facing reply for a conversational turn."""

    model_config = ConfigDict(extra="forbid")

    reply: str = Field(min_length=1, max_length=500)
    coaching_problem: str | None = Field(default=None, max_length=200)
    context_facts: list[UserContextFactDraft] = Field(default_factory=list, max_length=4)


@dataclass(frozen=True)
class GeneratedTextTurn:
    content: CoachContent
    coaching_problem: str | None
    context_facts: tuple[UserContextFactDraft, ...]

    def __getattr__(self, name: str) -> Any:
        """Keep existing CoachContent callers source-compatible during rollout."""
        return getattr(self.content, name)


class ModelNotConfiguredError(RuntimeError):
    """The server has no model credential."""


class ModelCallError(RuntimeError):
    """The external model did not return a usable structured response."""

    def __init__(self, message: str, *, error_code: str = "MODEL_RESPONSE_INVALID") -> None:
        super().__init__(message)
        self.error_code = error_code


class ModelAdapter(Protocol):
    """Provider-neutral contract used by the LangGraph runtime."""

    @property
    def is_configured(self) -> bool: ...

    async def observe(
        self,
        *,
        frame_paths: list[Path],
        media_kind: str,
        shot_profile: str,
        camera_view: str,
        handedness: str,
    ) -> VisionObservation: ...

    async def compose_coaching_turn_plan(
        self,
        *,
        context_packet: ContextPacket,
        observation: VisionObservation | None,
        base_assessment: BaseAssessment | None,
        media_kind: str | None,
    ) -> CoachingTurnPlan: ...

    async def compose_text_coach_content(
        self,
        *,
        context_packet: ContextPacket,
    ) -> GeneratedTextTurn: ...

    async def compose_conversation_reply(
        self,
        *,
        context_packet: ContextPacket,
    ) -> GeneratedTextTurn: ...

    async def compose_media_content(
        self,
        *,
        observation: VisionObservation,
        base_assessment: BaseAssessment,
        context: ShotContext,
        question: str,
        media_kind: str,
        policy: dict[str, Any],
    ) -> CoachContent: ...

    async def compose_text_content(
        self,
        *,
        message: str,
        context: ShotContext,
        history: list[dict[str, str]],
        latest_analysis: dict[str, Any] | None,
        policy: dict[str, Any],
    ) -> CoachContent: ...


def _image_mime_type(path: Path) -> str:
    return {
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "image/jpeg")


def _group_frames_by_media(frame_paths: list[Path]) -> list[list[Path]]:
    """Keep frames from each uploaded media item in one ordered group."""
    groups: list[list[Path]] = []
    group_indexes: dict[str, int] = {}
    for path in frame_paths:
        parent_name = path.parent.name
        group_key = str(path.parent) if parent_name.startswith("frames_") else str(path)
        group_index = group_indexes.get(group_key)
        if group_index is None:
            group_index = len(groups)
            group_indexes[group_key] = group_index
            groups.append([])
        groups[group_index].append(path)
    return groups


def _parse_response(
    response: types.GenerateContentResponse,
    schema: type[ResponseModel],
) -> ResponseModel:
    parsed = response.parsed
    if isinstance(parsed, schema):
        return parsed
    if isinstance(parsed, dict):
        return schema.model_validate(parsed)
    if response.text:
        return schema.model_validate_json(response.text)
    raise ModelCallError("Gemini response did not include structured output")


def _inline_schema_refs(
    node: Any,
    defs: dict[str, Any],
    resolving: frozenset[str],
) -> Any:
    """Replace every ``$ref`` with a deep copy of its ``$defs`` target.

    Sibling keys next to a ``$ref`` (e.g. an inlined ``description``) are kept and
    applied on top of the resolved definition, matching JSON Schema 2020-12.
    """
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            name = ref.rsplit("/", 1)[-1]
            if name in resolving:
                raise ModelCallError(
                    "Cannot project a recursive schema for structured output",
                    error_code="MODEL_REQUEST_INVALID",
                )
            target = defs.get(name)
            if target is None:
                raise ModelCallError(
                    "Structured output schema referenced an unknown definition",
                    error_code="MODEL_REQUEST_INVALID",
                )
            resolved = _inline_schema_refs(deepcopy(target), defs, resolving | {name})
            siblings = {
                key: _inline_schema_refs(value, defs, resolving)
                for key, value in node.items()
                if key != "$ref"
            }
            resolved.update(siblings)
            return resolved
        return {key: _inline_schema_refs(value, defs, resolving) for key, value in node.items()}
    if isinstance(node, list):
        return [_inline_schema_refs(item, defs, resolving) for item in node]
    return node


def _is_null_schema(node: Any) -> bool:
    return isinstance(node, dict) and node.get("type") == "null"


def _collapse_nullable_anyof(node: dict[str, Any]) -> dict[str, Any]:
    """Collapse ``anyOf: [X, {"type": "null"}]`` into ``X`` with a ``null`` type member.

    Pydantic renders ``T | None`` as a nullable ``anyOf`` union that Gemini's
    ``response_json_schema`` rejects. Non-nullable ``anyOf`` (e.g. an either/or on two
    properties) is left untouched so no field constraint is lost.
    """
    members = node["anyOf"]
    non_null = [member for member in members if not _is_null_schema(member)]
    if not any(_is_null_schema(member) for member in members) or len(non_null) != 1:
        return node
    target = non_null[0]
    if not isinstance(target, dict) or "type" not in target:
        return node
    collapsed = dict(target)
    declared = collapsed["type"]
    types = list(declared) if isinstance(declared, list) else [declared]
    if "null" not in types:
        types.append("null")
    collapsed["type"] = types
    for key, value in node.items():
        if key != "anyOf":
            collapsed.setdefault(key, value)
    return collapsed


def _normalize_for_provider(node: Any) -> Any:
    """Reduce transport-only constructs Gemini rejects, without touching the model.

    - Collapses Pydantic nullable ``anyOf`` unions into a single ``type``-list schema.
    - Drops ``default`` keys, which do not constrain generation.

    Strict validation keywords (``enum``, ``required``, ``additionalProperties``) are
    preserved, and the application still parses the response under the unchanged Pydantic
    model, so unknown fields, invalid enums and missing required fields are still rejected.
    """
    if isinstance(node, dict):
        working = {key: value for key, value in node.items() if key != "default"}
        if isinstance(working.get("anyOf"), list):
            working = _collapse_nullable_anyof(working)
        return {key: _normalize_for_provider(value) for key, value in working.items()}
    if isinstance(node, list):
        return [_normalize_for_provider(item) for item in node]
    return node


def _build_transport_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """Project a Pydantic JSON Schema into a self-contained transport schema.

    Gemini's ``response_json_schema`` accepts standard JSON Schema but rejects the
    unresolved ``$ref``/``$defs`` graph that ``model_json_schema()`` emits, plus Pydantic
    nullable ``anyOf`` unions and ``default`` keys, returning HTTP 400 ``INVALID_ARGUMENT``.
    We inline every ``$ref`` against ``$defs`` and normalize those constructs on a copy so
    the transport payload is self-contained. Validation keywords such as ``enum``,
    ``required`` and ``additionalProperties`` are preserved; the original model contract
    is never mutated, and the response is still parsed under strict Pydantic validation.
    """
    root = deepcopy(schema.model_json_schema())
    defs = root.pop("$defs", {})
    inlined = _inline_schema_refs(root, defs, frozenset())
    return _normalize_for_provider(inlined)


def _provider_error_code(error: errors.APIError) -> str:
    if error.code == 429:
        return "MODEL_RATE_LIMITED"
    if error.code in {401, 403}:
        return "MODEL_AUTH_FAILED"
    if error.code == 400:
        return "MODEL_REQUEST_INVALID"
    if error.code >= 500:
        return "MODEL_PROVIDER_UNAVAILABLE"
    return "MODEL_UNAVAILABLE"


class GeminiModelAdapter:
    """Bounded Gemini adapter for text and extracted-frame observation calls."""

    def __init__(
        self,
        settings: Settings,
        client: genai.Client | None = None,
        *,
        max_attempts: int = MODEL_MAX_ATTEMPTS,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        self.model = settings.gemini_model
        self._retry_delay_seconds = settings.model_retry_delay_seconds
        self._max_attempts = max_attempts
        api_key = settings.model_api_key
        self._client = client or (genai.Client(api_key=api_key) if api_key else None)

    @property
    def is_configured(self) -> bool:
        return self._client is not None

    def _require_client(self) -> genai.Client:
        if self._client is None:
            raise ModelNotConfiguredError("GEMINI_API_KEY is not configured")
        return self._client

    async def _generate_structured(
        self,
        *,
        contents: str | list[str | types.Part],
        schema: type[ResponseModel],
    ) -> ResponseModel:
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._require_client().aio.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_json_schema=_build_transport_schema(schema),
                    ),
                )
                return _parse_response(response, schema)
            except errors.APIError as error:
                if attempt < self._max_attempts and error.code in RETRYABLE_MODEL_STATUS_CODES:
                    logger.warning(
                        "Retrying Gemini structured response after HTTP %s",
                        error.code,
                    )
                    await asyncio.sleep(self._retry_delay_seconds)
                    continue
                raise ModelCallError(
                    "Gemini API call failed",
                    error_code=_provider_error_code(error),
                ) from error
            except (ValidationError, ValueError) as error:
                raise ModelCallError(
                    "Gemini structured response validation failed",
                    error_code="MODEL_RESPONSE_INVALID",
                ) from error
        raise AssertionError("Gemini retry loop ended without a result")

    async def observe(
        self,
        *,
        frame_paths: list[Path],
        media_kind: str,
        shot_profile: str,
        camera_view: str,
        handedness: str,
    ) -> VisionObservation:
        """Observe frames without receiving user question, FEEL, or shot result."""
        frame_groups = _group_frames_by_media(frame_paths)
        media_count = len(frame_groups)
        prompt = (
            "당신은 골프 영상의 시각 관찰 후보만 만드는 분석기다. 사용자 질문, 느낌, "
            "샷 결과, 과거 코칭 주제, 로드맵은 제공되지 않았으며 추측하지 않는다. 각 관찰은 "
            "[대상]+[기준]+[시점]+[상태]가 드러나게 작성한다. 2D 프레임으로 Club Path, "
            "Face Angle, Face-to-Path, Attack Angle, Low Point, Ground Reaction Force 수치를 "
            "확정하지 않는다. 프레임에 골퍼와 골프 동작이 없으면 is_golf_media=false로 한다. "
            "각 관찰에는 고정 우선순위 판정에 사용할 assessment_category를 하나 배정한다. "
            "카테고리는 impact_structure, transition_sequence, arm_body_space, center_posture, "
            "backswing, tempo_shape 중 하나다. "
            f"입력 종류={media_kind}, 스윙 프로필={shot_profile}, 촬영 각도={camera_view}, "
            f"주 사용 손={handedness}. "
            "사진 한 장이면 동작 순서, 템포, 전환 원인을 관찰로 만들지 않는다. "
            f"서로 구분된 미디어 수={media_count}. 미디어가 둘 이상이면 각 경계 뒤의 프레임만 "
            "해당 미디어의 시간순 프레임으로 취급하고 서로 하나의 연속 동작으로 합치지 않는다. "
            "각 observation의 subject 또는 state에 미디어 A, 미디어 B처럼 출처를 명시한다. "
            "같은 스윙 구간을 대응시킬 수 있으면 두 미디어의 직접 보이는 차이를 최소 하나 "
            "observation으로 작성한다. 대응 구간이나 차이를 신뢰할 수 없으면 차이를 만들지 말고 "
            "cannot_determine에 그 이유를 기록한다."
        )
        contents: list[str | types.Part] = [prompt]
        for index, group in enumerate(frame_groups):
            label = chr(ord("A") + index)
            contents.append(
                f"[미디어 {label} 시작] 다음 {len(group)}장은 미디어 {label}에서 시간순으로 "
                "추출한 프레임이다. 다른 미디어와 섞지 않는다."
            )
            contents.extend(
                types.Part.from_bytes(data=path.read_bytes(), mime_type=_image_mime_type(path))
                for path in group
            )
            contents.append(f"[미디어 {label} 끝]")
        return await self._generate_structured(contents=contents, schema=VisionObservation)

    async def compose_coaching_turn_plan(
        self,
        *,
        context_packet: ContextPacket,
        observation: VisionObservation | None,
        base_assessment: BaseAssessment | None,
        media_kind: str | None,
    ) -> CoachingTurnPlan:
        """Build one candidate-only coaching plan from a frozen context packet."""
        payload = {
            "context_packet": context_packet.model_dump(mode="json"),
            "current_observation": observation.model_dump(mode="json") if observation else None,
            "frozen_base_assessment": (
                base_assessment.model_dump(mode="json") if base_assessment else None
            ),
            "media_kind": media_kind,
        }
        prompt = (
            "당신은 Java가 최종 검증하고 저장할 CoachingTurnPlan 후보만 만든다. "
            "상태를 확정하거나 최종 사용자 문장을 조립하지 않는다. "
            "미디어 turn이면 current_observation과 frozen_base_assessment는 이미 질문과 FEEL 없이 "
            "동결된 근거다. 이 값을 바꾸거나 새 observation을 만들지 않는다. "
            "텍스트 turn이면 evidence_mode=text_only, observation_indexes=[], "
            "base_assessment_hash=null이다. "
            "Progress, Roadmap, Reframe 후보에는 반드시 구체적인 evidence_references를 둔다. "
            "사용자 체감만으로 영상 개선이나 milestone 완료를 선언하지 않는다. "
            "Recognition은 근거 수준을 넘지 않는다. 한 turn에는 핵심 후보만 제한적으로 만든다. "
            "rejected 또는 분석 실패 상태는 이 호출 대상이 아니다. "
            "반환은 CoachingTurnPlan JSON 하나이며 내부 필드명을 사용자 문장처럼 노출하지 않는다.\n"
            + json.dumps(payload, ensure_ascii=False)
        )
        return await self._generate_structured(contents=prompt, schema=CoachingTurnPlan)

    async def compose_text_coach_content(
        self,
        *,
        context_packet: ContextPacket,
    ) -> GeneratedTextTurn:
        """Generate language fields, then build the strict evidence contract locally."""
        payload = {"context_packet": context_packet.model_dump(mode="json")}
        prompt = (
            "당신은 골프 코치와 사용자가 실제로 대화하는 것처럼 짧고 자연스러운 답변 초안만 "
            "만든다. 기능명세서처럼 제목과 판정 항목을 나열하지 않는다. context_packet의 현재 "
            "질문에 먼저 직접 답하고, 활성 코칭 주제가 있으면 그 문제와 연결한다. 영상에서 직접 "
            "확인하지 않은 동작은 확정하지 않는다. 가능한 원인은 필요할 때만 중요한 순서대로 최대 "
            "세 개까지 causal_chain에 둔다. 사용자가 이번에 바꿀 동작은 많아도 하나만 제안한다. "
            "추가 정보가 꼭 필요할 때만 follow_up_question에 사용자가 그대로 읽을 수 있는 완성된 "
            "질문 한 문장을 쓰고, 필요 없으면 null로 둔다. coaching_problem에는 현재 대화에서 "
            "우선 다룰 코칭 문제를 짧게 쓰되 문제를 특정할 근거가 없으면 null로 둔다. "
            "context_facts는 "
            "현재 사용자 발화에 직접 명시된 신체 특징, 부상, 현재 스윙 스타일, 지향 스윙 스타일만 "
            "추출한다. 추정하거나 영상 관찰을 섞지 않는다. "
            "부상이 나았다고 직접 말하면 REMOVE를 쓴다. "
            "특정 클럽에 한정된 진술일 때만 use_current_shot_scope=true로 둔다. FEEL, OBSERVATION, "
            "계약, 스키마 같은 내부 용어는 사용자에게 노출하지 않는다.\n"
            + json.dumps(payload, ensure_ascii=False)
        )
        draft = await self._generate_structured(contents=prompt, schema=TextCoachDraft)
        return GeneratedTextTurn(
            content=CoachContent(
                evidence_mode="text_only",
                direct_answer=draft.direct_answer,
                causal_chain=draft.causal_chain,
                evidence_boundary="현재 대화 맥락만 사용한 텍스트 코칭입니다.",
                cannot_determine=draft.cannot_determine,
                observation_indexes=[],
                base_assessment_hash=None,
                single_change=draft.single_change,
                verification=draft.verification,
                preserve_candidate=None,
                preserve_topic=None,
                follow_up_information_needed=draft.follow_up_question,
            ),
            coaching_problem=draft.coaching_problem,
            context_facts=tuple(draft.context_facts),
        )

    async def compose_conversation_reply(
        self,
        *,
        context_packet: ContextPacket,
    ) -> GeneratedTextTurn:
        """Generate one short conversational reply without coaching-plan fields."""
        topic = context_packet.active_coaching_topic
        payload = {
            "user_message": context_packet.request_context.user_message,
            "active_topic": (
                {
                    "user_problem": topic.user_problem,
                    "root_problem": topic.root_problem,
                    "current_experiment": topic.current_experiment,
                    "carry_forward_feel": topic.carry_forward_feel,
                }
                if topic is not None
                else None
            ),
            "recent_dialogue": [
                {"role": message.role, "content": message.content}
                for message in context_packet.recent_dialogue[-6:]
            ],
            "relevant_user_context": [
                {
                    "fact_type": fact.fact_type,
                    "body_region": fact.body_region,
                    "statement": fact.statement,
                    "expires_at": fact.expires_at.isoformat() if fact.expires_at else None,
                }
                for fact in context_packet.relevant_user_context_facts
            ],
        }
        prompt = (
            "당신은 사용자와 대화하는 골프 코치다. 현재 발화에 먼저 반응하고, 답변은 자연스러운 "
            "한국어 최대 두 문장으로 끝낸다. 이 입력은 아직 원인 분석보다 대화로 문제를 좁혀야 "
            "하는 단계다. 확인되지 않은 원인, 교정 동작, 연습법을 먼저 나열하지 않는다. 필요한 "
            "경우에만 마지막에 선택하기 쉬운 질문 하나를 한다. coaching_problem에는 지금 이어갈 "
            "골프 코칭 문제를 짧게 쓰고, 골프 문제가 아니거나 특정할 수 없으면 null로 둔다. "
            "relevant_user_context는 현재 질문과 관련될 때만 자연스럽게 반영하고 저장 항목처럼 "
            "나열하지 않는다. "
            "context_facts에는 현재 발화에 사용자가 직접 밝힌 신체 특징, 부상, 현재 스윙 스타일, "
            "지향 스윙 스타일만 넣는다. 추정하지 않는다. 부상이 나았다고 직접 말한 경우 REMOVE를 "
            "쓴다. 특정 클럽 진술일 때만 use_current_shot_scope=true다. 제목, 목록, 내부 용어를 "
            "사용자 답변에 쓰지 않는다.\n" + json.dumps(payload, ensure_ascii=False)
        )
        draft = await self._generate_structured(contents=prompt, schema=ConversationDraft)
        return GeneratedTextTurn(
            content=CoachContent(
                evidence_mode="text_only",
                direct_answer=draft.reply.strip(),
                causal_chain=[],
                evidence_boundary="대화형 응답이며 새로운 스윙 판정을 포함하지 않습니다.",
                cannot_determine=[],
                observation_indexes=[],
            ),
            coaching_problem=draft.coaching_problem,
            context_facts=tuple(draft.context_facts),
        )

    async def compose_media_content(
        self,
        *,
        observation: VisionObservation,
        base_assessment: BaseAssessment,
        context: ShotContext,
        question: str,
        media_kind: str,
        policy: dict[str, Any],
    ) -> CoachContent:
        """Compose compact media coaching content from the frozen visual assessment."""
        payload = {
            "observation": observation.model_dump(mode="json"),
            "frozen_base_assessment": base_assessment.model_dump(mode="json"),
            "selected_context": context.model_dump(mode="json"),
            "user_question_or_feel": question,
            "media_kind": media_kind,
            "conversation_policy": policy,
        }
        prompt = (
            "당신은 사용자에게 보여 주기 전의 골프 코칭 내용만 만든다. frozen_base_assessment는 "
            "질문을 보지 않고 생성된 고정 판정이다. 질문 표현에 맞춰 판정 순서, 중요도, 관찰 "
            "근거를 바꾸거나 새 관찰을 만들지 않는다. analysis_goal이 comparison이면 미디어 A와 "
            "미디어 B를 함께 명시하고, observation에 기록된 직접 비교 중 중요도가 가장 높은 차이 "
            "하나를 direct_answer의 첫 문장으로 답한다. 공통 동작만 설명하거나 한 영상의 특징만 "
            "말해서 비교를 대체하지 않는다. 직접 비교 observation이 없으면 비슷하다고 추정하지 "
            "말고 신뢰할 수 있는 차이를 확인하지 못했다고 답한다.\n"
            + json.dumps(payload, ensure_ascii=False)
        )
        return await self._generate_structured(contents=prompt, schema=CoachContent)

    async def compose_text_content(
        self,
        *,
        message: str,
        context: ShotContext,
        history: list[dict[str, Any]],
        latest_analysis: dict[str, Any] | None,
        policy: dict[str, Any],
    ) -> CoachContent:
        """Legacy text-only content composition kept for narrow compatibility tests."""
        selected_context = context.model_dump(mode="json") if policy["context_relevant"] else None
        payload = {
            "selected_context_if_relevant": selected_context,
            "recent_history": history,
            "latest_validated_analysis": latest_analysis,
            "user_message": message,
            "conversation_policy": policy,
        }
        prompt = (
            "당신은 사용자에게 보여 주기 전의 골프 코칭 내용만 만든다. 현재 turn에는 영상이 "
            "없으므로 evidence_mode=text_only, observation_indexes=[], base_assessment_hash=null로 "
            "쓴다. 새 영상 관찰을 만들지 않는다. 가능한 원인은 중요한 순서대로 최대 두 개만 둔다.\n"
            + json.dumps(payload, ensure_ascii=False)
        )
        return await self._generate_structured(contents=prompt, schema=CoachContent)
