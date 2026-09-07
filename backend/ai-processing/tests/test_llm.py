import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from google.genai import errors

from app.config import Settings
from app.domain.models import (
    CoachContent,
    CoachingTurnPlan,
    ContextPacket,
    ShotContext,
    VisionObservation,
)
from app.llm import (
    GeminiModelAdapter,
    ModelCallError,
    ModelNotConfiguredError,
    _build_transport_schema,
)


def _schema_contains_ref(node: Any) -> bool:
    if isinstance(node, dict):
        if "$ref" in node or "$defs" in node:
            return True
        return any(_schema_contains_ref(value) for value in node.values())
    if isinstance(node, list):
        return any(_schema_contains_ref(item) for item in node)
    return False


def _schema_has_key(node: Any, key: str) -> bool:
    if isinstance(node, dict):
        if key in node:
            return True
        return any(_schema_has_key(value, key) for value in node.values())
    if isinstance(node, list):
        return any(_schema_has_key(item, key) for item in node)
    return False


def make_settings(*, api_key: str | None = "gemini-test-key") -> Settings:
    return Settings(
        supabase_url="https://project.supabase.co",
        gemini_api_key=api_key,
        model_retry_delay_seconds=0,
    )


def make_context() -> ShotContext:
    return ShotContext(
        shot_profile="full_swing",
        club="7번 아이언",
        camera_view="face_on",
        handedness="right",
        analysis_goal="posture_correction",
    )


def make_policy(*, context_relevant: bool = False) -> dict[str, Any]:
    return {
        "response_mode": "short",
        "question_allowed": True,
        "question_preferred": False,
        "preferred_invite_mode": None,
        "positive_allowed": False,
        "allowed_invite_modes": ["compare_good_bad"],
        "blocked_positive_topics": [],
        "user_detail_anchor": "골프 잘 치고 싶엉",
        "context_relevant": context_relevant,
        "tone": "casual",
    }


def make_text_content() -> CoachContent:
    return CoachContent(
        evidence_mode="text_only",
        direct_answer="반복되는 미스 하나부터 줄이면 돼.",
        causal_chain=["여러 동작을 동시에 바꾸면 원인을 구분하기 어렵다."],
        evidence_boundary="현재 대화의 내용만 사용함",
        cannot_determine=[],
        observation_indexes=[],
        single_change="최근 가장 잦은 미스 하나를 정한다.",
        verification="같은 클럽으로 다섯 번 확인한다.",
    )


class FakeResponse:
    def __init__(self, parsed: Any) -> None:
        self.parsed = parsed
        self.text = None


class FakeModels:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def generate_content(self, **values: Any) -> FakeResponse:
        self.calls.append(values)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return FakeResponse(response)


class FakeAio:
    def __init__(self, models: FakeModels) -> None:
        self.models = models


class FakeGeminiClient:
    def __init__(self, responses: list[Any]) -> None:
        self.models = FakeModels(responses)
        self.aio = FakeAio(self.models)


class GeminiModelAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_coaching_turn_plan_uses_context_packet_schema(self) -> None:
        fixture_root = Path(__file__).resolve().parents[2] / "contracts" / "fixtures"
        request_body = json.loads(
            (fixture_root / "text-coaching-request.json").read_text(encoding="utf-8")
        )
        response_body = json.loads(
            (fixture_root / "text-coaching-response.json").read_text(encoding="utf-8")
        )
        request = ContextPacket.model_validate(request_body["context_packet"])
        expected = CoachingTurnPlan.model_validate(response_body["coaching_turn_plan"])
        client = FakeGeminiClient([expected])
        adapter = GeminiModelAdapter(make_settings(), client=client)  # type: ignore[arg-type]

        result = await adapter.compose_coaching_turn_plan(
            context_packet=request,
            observation=None,
            base_assessment=None,
            media_kind=None,
        )

        self.assertEqual(result, expected)
        call = client.models.calls[0]
        self.assertIsNone(call["config"].response_schema)
        self.assertEqual(
            call["config"].response_json_schema, _build_transport_schema(CoachingTurnPlan)
        )
        self.assertFalse(_schema_contains_ref(call["config"].response_json_schema))
        self.assertIn("context_packet", call["contents"])

    async def test_text_content_uses_schema_without_injecting_irrelevant_defaults(self) -> None:
        expected = make_text_content()
        client = FakeGeminiClient([expected])
        adapter = GeminiModelAdapter(make_settings(), client=client)  # type: ignore[arg-type]

        result = await adapter.compose_text_content(
            message="골프 잘 치고 싶엉",
            context=make_context(),
            history=[],
            latest_analysis=None,
            policy=make_policy(context_relevant=False),
        )

        self.assertEqual(result, expected)
        call = client.models.calls[0]
        self.assertEqual(call["model"], "gemini-3.6-flash")
        self.assertIsNone(call["config"].response_schema)
        self.assertEqual(call["config"].response_json_schema, _build_transport_schema(CoachContent))
        self.assertNotIn("7번 아이언", call["contents"])
        self.assertIn("현재 turn에는 영상이", call["contents"])
        self.assertIn("최대 두 개", call["contents"])

    async def test_observation_sends_image_bytes_and_blind_context_only(self) -> None:
        expected = VisionObservation(
            is_golf_media=False,
            golf_media_reason="골프 장면이 보이지 않음",
            observations=[],
            cannot_determine=[],
        )
        client = FakeGeminiClient([expected])
        adapter = GeminiModelAdapter(make_settings(), client=client)  # type: ignore[arg-type]

        with TemporaryDirectory() as temp_directory:
            image_path = Path(temp_directory) / "frame.jpg"
            image_path.write_bytes(b"jpeg-bytes")
            result = await adapter.observe(
                frame_paths=[image_path],
                media_kind="video",
                shot_profile="full_swing",
                camera_view="face_on",
                handedness="right",
            )

        self.assertEqual(result, expected)
        call = client.models.calls[0]
        self.assertEqual(len(call["contents"]), 2)
        self.assertNotIn("왼쪽으로 밀리는 느낌", call["contents"][0])
        self.assertEqual(call["contents"][1].inline_data.mime_type, "image/jpeg")
        self.assertIsNone(call["config"].response_schema)
        self.assertEqual(
            call["config"].response_json_schema, _build_transport_schema(VisionObservation)
        )

    async def test_structured_call_sends_inlined_json_schema_not_pydantic_schema(self) -> None:
        # Regression: Gemini rejected the Pydantic-native schema graph with HTTP 400
        # INVALID_ARGUMENT. The common structured-output call must send a self-contained
        # response_json_schema (refs inlined) while keeping strict object contracts intact.
        expected = make_text_content()
        client = FakeGeminiClient([expected])
        adapter = GeminiModelAdapter(make_settings(), client=client)  # type: ignore[arg-type]

        await adapter.compose_text_content(
            message="테스트",
            context=make_context(),
            history=[],
            latest_analysis=None,
            policy=make_policy(),
        )

        config = client.models.calls[0]["config"]
        self.assertIsNone(config.response_schema)
        self.assertEqual(config.response_json_schema, _build_transport_schema(CoachContent))
        self.assertEqual(config.response_mime_type, "application/json")
        # Strict object contract must survive projection; refs must be resolved away.
        self.assertIs(config.response_json_schema["additionalProperties"], False)
        self.assertFalse(_schema_contains_ref(config.response_json_schema))

    def test_transport_schema_inlines_refs_without_mutating_model(self) -> None:
        before = CoachingTurnPlan.model_json_schema()
        transport = _build_transport_schema(CoachingTurnPlan)
        after = CoachingTurnPlan.model_json_schema()

        # The canonical Pydantic schema keeps its $defs/$ref graph and is not mutated.
        self.assertEqual(before, after)
        self.assertIn("$defs", before)
        # The transport projection is fully self-contained.
        self.assertNotIn("$defs", transport)
        self.assertFalse(_schema_contains_ref(transport))
        # Validation keywords stay intact so the provider still constrains generation.
        self.assertIs(transport["additionalProperties"], False)
        self.assertEqual(
            transport["properties"]["coach_content"]["properties"]["evidence_mode"]["enum"],
            ["text_only", "photo_limited", "video_ready"],
        )

    def test_transport_schema_normalizes_nullable_unions_and_drops_defaults(self) -> None:
        transport = _build_transport_schema(CoachContent)

        self.assertFalse(_schema_contains_ref(transport))
        # Provider-incompatible constructs are normalized away on the transport copy.
        self.assertFalse(_schema_has_key(transport, "default"))
        self.assertFalse(_schema_has_key(transport, "anyOf"))
        # Nullable fields collapse into a type-list that still allows null.
        single_change = transport["properties"]["single_change"]
        self.assertIn("string", single_change["type"])
        self.assertIn("null", single_change["type"])
        self.assertEqual(single_change["maxLength"], 500)
        # The canonical Pydantic model still declares defaults and nullable unions.
        self.assertTrue(_schema_has_key(CoachContent.model_json_schema(), "anyOf"))

    async def test_compose_text_coach_content_uses_coach_content_transport_schema(self) -> None:
        fixture_root = Path(__file__).resolve().parents[2] / "contracts" / "fixtures"
        request_body = json.loads(
            (fixture_root / "text-coaching-request.json").read_text(encoding="utf-8")
        )
        packet = ContextPacket.model_validate(request_body["context_packet"])
        expected = make_text_content()
        client = FakeGeminiClient([expected])
        adapter = GeminiModelAdapter(make_settings(), client=client)  # type: ignore[arg-type]

        result = await adapter.compose_text_coach_content(context_packet=packet)

        self.assertEqual(result, expected)
        call = client.models.calls[0]
        self.assertIsNone(call["config"].response_schema)
        self.assertEqual(call["config"].response_json_schema, _build_transport_schema(CoachContent))
        self.assertIn("context_packet", call["contents"])

    async def test_invalid_model_output_is_rejected_by_strict_pydantic_parse(self) -> None:
        # Loosening the transport projection must not loosen the application contract:
        # unknown fields, invalid enums and missing required fields still fail parsing.
        valid = make_text_content().model_dump(mode="json")
        unknown_field = {**valid, "bogus": "x"}
        invalid_enum = {**valid, "evidence_mode": "not_a_mode"}
        missing_required = {key: value for key, value in valid.items() if key != "direct_answer"}

        for payload in (unknown_field, invalid_enum, missing_required):
            client = FakeGeminiClient([payload])
            adapter = GeminiModelAdapter(make_settings(), client=client)  # type: ignore[arg-type]
            with self.assertRaises(ModelCallError) as raised:
                await adapter.compose_text_content(
                    message="테스트",
                    context=make_context(),
                    history=[],
                    latest_analysis=None,
                    policy=make_policy(),
                )
            self.assertEqual(raised.exception.error_code, "MODEL_RESPONSE_INVALID")

    async def test_missing_key_is_explicit(self) -> None:
        adapter = GeminiModelAdapter(make_settings(api_key=None))

        with self.assertRaises(ModelNotConfiguredError):
            await adapter.compose_text_content(
                message="테스트",
                context=make_context(),
                history=[],
                latest_analysis=None,
                policy=make_policy(),
            )

    async def test_retries_one_transient_provider_failure(self) -> None:
        expected = make_text_content()
        unavailable = errors.APIError(
            503,
            {"error": {"code": 503, "message": "temporary", "status": "UNAVAILABLE"}},
        )
        client = FakeGeminiClient([unavailable, expected])
        adapter = GeminiModelAdapter(make_settings(), client=client)  # type: ignore[arg-type]

        result = await adapter.compose_text_content(
            message="테스트",
            context=make_context(),
            history=[],
            latest_analysis=None,
            policy=make_policy(),
        )

        self.assertEqual(result, expected)
        self.assertEqual(len(client.models.calls), 2)

    async def test_exposes_rate_limit_after_bounded_retry(self) -> None:
        rate_limited = errors.APIError(
            429,
            {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}},
        )
        client = FakeGeminiClient([rate_limited, rate_limited])
        adapter = GeminiModelAdapter(make_settings(), client=client)  # type: ignore[arg-type]

        with self.assertRaises(ModelCallError) as raised:
            await adapter.compose_text_content(
                message="테스트",
                context=make_context(),
                history=[],
                latest_analysis=None,
                policy=make_policy(),
            )

        self.assertEqual(raised.exception.error_code, "MODEL_RATE_LIMITED")
        self.assertEqual(len(client.models.calls), 2)

    async def test_single_attempt_mode_does_not_retry_paid_internal_call(self) -> None:
        rate_limited = errors.APIError(
            429,
            {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}},
        )
        client = FakeGeminiClient([rate_limited])
        adapter = GeminiModelAdapter(  # type: ignore[arg-type]
            make_settings(),
            client=client,
            max_attempts=1,
        )

        with self.assertRaises(ModelCallError):
            await adapter.compose_text_content(
                message="테스트",
                context=make_context(),
                history=[],
                latest_analysis=None,
                policy=make_policy(),
            )

        self.assertEqual(len(client.models.calls), 1)


if __name__ == "__main__":
    unittest.main()
