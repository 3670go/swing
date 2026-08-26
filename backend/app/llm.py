import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Protocol, TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.schemas import (
    BaseAssessment,
    CoachContent,
    ConversationReply,
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

    async def write_conversation(
        self,
        *,
        user_message: str,
        history: list[dict[str, Any]],
        content: CoachContent,
        policy: dict[str, Any],
    ) -> ConversationReply: ...


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

    def __init__(self, settings: Settings, client: genai.Client | None = None) -> None:
        self.model = settings.gemini_model
        self._retry_delay_seconds = settings.model_retry_delay_seconds
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
        for attempt in range(1, MODEL_MAX_ATTEMPTS + 1):
            try:
                response = await self._require_client().aio.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=schema,
                    ),
                )
                return _parse_response(response, schema)
            except errors.APIError as error:
                if attempt < MODEL_MAX_ATTEMPTS and error.code in RETRYABLE_MODEL_STATUS_CODES:
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
            "샷 결과는 제공되지 않았으며 추측하지 않는다. 각 관찰은 "
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
        """Build evidence-bounded coaching content from a frozen assessment."""
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
            "근거를 바꾸거나 새 관찰을 만들지 않는다. direct_answer에는 사용자의 질문에 대한 "
            "핵심 답을 쓰고 causal_chain은 최대 세 단계로 제한한다. observation_indexes는 실제로 "
            "사용한 관찰의 0 기반 인덱스만 쓴다. base_assessment_hash는 입력과 정확히 같아야 한다. "
            "영상이면 evidence_mode=video_ready, 사진이면 photo_limited다. 사진으로 동작 순서, "
            "템포, 전환 원인을 확정하지 않는다. single_change는 한 번에 하나만 제시하고 "
            "verification은 사용자가 결과를 확인하는 방법으로 쓴다. preserve_candidate는 현재 "
            "관찰에서 실제로 보존할 장점이 있을 때만 작성하며 빈 칭찬은 금지한다. 사용자 느낌은 "
            "답변 맥락일 뿐 고정 판정을 수정하는 근거가 아니다. 이 단계는 내부 내용 생성이므로 "
            "대화형 인사, 공감, 질문은 만들지 않는다.\n" + json.dumps(payload, ensure_ascii=False)
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
        """Build text-only coaching content without inventing current media evidence."""
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
            "쓴다. 새 영상 관찰을 만들지 않는다. 최신 검증 분석이 있으면 그 내용만 이전 영상의 "
            "근거로 재사용한다. 사용자 느낌은 니즈를 이해하는 참고 정보이지 실제 동작의 증거가 "
            "아니다. 가능한 원인은 중요한 순서대로 최대 두 개만 둔다. "
            "selected_context_if_relevant가 "
            "null이면 기본 클럽·촬영 각도·분석 목표를 답에 끌어오지 않는다. direct_answer에는 먼저 "
            "직접 답하고 causal_chain에는 필요한 인과만 쓴다. single_change와 verification은 정말 "
            "필요할 때만 작성한다. preserve_candidate는 최신 검증 분석에서 보존할 장점이 확인된 "
            "경우만 작성한다. 이 단계는 내부 내용 생성이므로 인사, 공감, 대화 유도 문장은 만들지 "
            "않는다.\n" + json.dumps(payload, ensure_ascii=False)
        )
        return await self._generate_structured(contents=prompt, schema=CoachContent)

    async def write_conversation(
        self,
        *,
        user_message: str,
        history: list[dict[str, Any]],
        content: CoachContent,
        policy: dict[str, Any],
    ) -> ConversationReply:
        """Turn approved coaching content into a compact, human chat response."""
        preserve = None
        if policy["positive_allowed"] and content.preserve_candidate:
            preserve = {
                "message": content.preserve_candidate,
                "topic": content.preserve_topic,
            }
        payload = {
            "user_message": user_message,
            "recent_dialogue": history[-6:],
            "what_to_say": {
                "answer": content.direct_answer,
                "reasons": content.causal_chain,
                "one_change": content.single_change,
                "how_to_check": content.verification,
                "extra_information_only_if_needed": content.follow_up_information_needed,
                "preserve_if_natural": preserve,
            },
            "conversation_limits": policy,
        }
        prompt = (
            "너는 앱 채팅창에서 사용자와 말로 대화하는 골프 코치다. what_to_say 안의 내용만 "
            "사용하고 새로운 판정이나 관찰을 추가하지 않는다. message는 사용자의 마지막 말에 먼저 "
            "반응한 뒤 핵심 답과 이유를 자연스럽게 이어 쓴다. 사용자가 자세한 설명을 요청하지 "
            "않았다면 짧은 두 문단 이내로 쓴다. 제목, 항목명, 보고서 형식, 불릿 목록, 영문 내부 "
            "필드명은 쓰지 않는다. 사용자가 묻지 않은 기본 클럽·촬영 각도·분석 목표를 꺼내지 "
            "않는다. 영상이 없다는 안내를 습관적으로 붙이거나 영상을 먼저 요구하지 않는다. "
            "conversation_limits.tone=casual이면 반드시 짧은 반말의 해체로 답하고, '합니다', "
            "'입니다', '때문입니다', '파악해야 합니다' 같은 보고서 말투를 쓰지 않는다. 예를 들어 "
            "'골프 실력을 체계적으로 향상시키려면 정확하게 파악해야 합니다'처럼 시작하지 말고 "
            "'좋지. 우선 요즘 제일 자주 나오는 미스 하나부터 잡아보자'처럼 말한다. tone=polite면 "
            "짧은 해요체를 쓴다. "
            "positive_feedback은 preserve_if_natural이 있을 때만 간헐적으로 사용한다. 질문은 답에 "
            "따라 다음 설명이 실제로 달라질 때만 follow_up_question에 한 개 쓰고 message 안에는 "
            "물음표를 넣지 않는다. conversation_limits가 질문을 막으면 질문 필드는 null이고 "
            "invite_mode=none이다. 사용자의 표현을 그대로 반복해 공감한 척하지 말고, 그 표현에서 "
            "설명할 가치가 있는 차이를 짚어 대화를 이어 간다.\n"
            + json.dumps(payload, ensure_ascii=False)
        )
        return await self._generate_structured(contents=prompt, schema=ConversationReply)
