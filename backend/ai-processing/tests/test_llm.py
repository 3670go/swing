import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from google.genai import errors

from app.config import Settings
from app.domain.models import CoachContent, ConversationReply, ShotContext, VisionObservation
from app.llm import GeminiModelAdapter, ModelCallError, ModelNotConfiguredError


def make_settings(*, api_key: str | None = "gemini-test-key") -> Settings:
    return Settings(
        database_url="postgresql://user:secret@host:6543/postgres",
        supabase_url="https://project.supabase.co",
        supabase_secret_key="server-secret-key",
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
        self.assertIs(call["config"].response_schema, CoachContent)
        self.assertNotIn("7번 아이언", call["contents"])
        self.assertIn("현재 turn에는 영상이", call["contents"])
        self.assertIn("최대 두 개", call["contents"])

    async def test_conversation_writer_receives_content_not_analysis_contract(self) -> None:
        expected = ConversationReply(message="좋아. 반복되는 미스 하나부터 줄여보자.")
        client = FakeGeminiClient([expected])
        adapter = GeminiModelAdapter(make_settings(), client=client)  # type: ignore[arg-type]

        result = await adapter.write_conversation(
            user_message="골프 잘 치고 싶엉",
            history=[],
            content=make_text_content(),
            policy=make_policy(),
        )

        self.assertEqual(result, expected)
        call = client.models.calls[0]
        self.assertIs(call["config"].response_schema, ConversationReply)
        self.assertNotIn("frozen_base_assessment", call["contents"])
        self.assertNotIn("7번 아이언", call["contents"])
        self.assertIn("보고서 형식", call["contents"])
        self.assertIn("영상을 먼저 요구하지 않는다", call["contents"])
        self.assertIn("짧은 반말의 해체", call["contents"])

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
        self.assertIs(call["config"].response_schema, VisionObservation)

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
