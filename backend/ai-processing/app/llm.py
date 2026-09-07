import asyncio
import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol, TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.domain.models import (
    BaseAssessment,
    CoachContent,
    CoachingTurnPlan,
    ContextPacket,
    ShotContext,
    VisionObservation,
)

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)
MODEL_MAX_ATTEMPTS = 2
RETRYABLE_MODEL_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
logger = logging.getLogger(__name__)


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
    ) -> CoachContent: ...

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
            "사진 한 장이면 동작 순서, 템포, 전환 원인을 관찰로 만들지 않는다."
        )
        contents: list[str | types.Part] = [prompt]
        contents.extend(
            types.Part.from_bytes(data=path.read_bytes(), mime_type=_image_mime_type(path))
            for path in frame_paths
        )
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
    ) -> CoachContent:
        """Generate a small text-only CoachContent from the frozen context packet.

        The text turn asks Gemini for CoachContent only, not the full CoachingTurnPlan,
        so the provider receives a compact schema. The graph then wraps this content into
        a CoachingTurnPlan deterministically. evidence_mode must remain text_only.
        """
        payload = {"context_packet": context_packet.model_dump(mode="json")}
        prompt = (
            "당신은 사용자에게 보여 주기 전의 골프 코칭 내용(CoachContent)만 만든다. "
            "현재 turn에는 영상이 없으므로 evidence_mode=text_only, observation_indexes=[], "
            "base_assessment_hash=null로 쓴다. 새 영상 관찰을 만들지 않는다. "
            "context_packet의 현재 질문과 활성 코칭 주제를 이어서 답하고, 가능한 원인은 "
            "중요한 순서대로 최대 세 개까지만 causal_chain에 둔다. 내부 필드명을 사용자 문장처럼 "
            "노출하지 않는다.\n" + json.dumps(payload, ensure_ascii=False)
        )
        return await self._generate_structured(contents=prompt, schema=CoachContent)

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
        """Legacy content-only media composition kept for narrow compatibility tests."""
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
            "근거를 바꾸거나 새 관찰을 만들지 않는다.\n" + json.dumps(payload, ensure_ascii=False)
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
