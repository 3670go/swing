import copy
import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.internal_api import get_internal_service, internal_app
from app.internal_schemas import (
    InternalAnalysisResponse,
    InternalTextCoachingResponse,
)
from app.services.internal_processing import InternalAnalysisResult

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "contracts" / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def authorization_header() -> dict[str, str]:
    return {"Authorization": "Bearer internal-test-token"}


def make_settings() -> Settings:
    return Settings(
        supabase_url="https://project.supabase.co",
        gemini_api_key="gemini-test-key",
        internal_api_token="internal-test-token",
    )


class FakeInternalService:
    is_model_configured = True

    async def analyze(self, _command) -> InternalAnalysisResult:
        fixture = InternalAnalysisResponse.model_validate(load_fixture("analysis-response.json"))
        return InternalAnalysisResult(
            status=fixture.status,
            observation=fixture.observation,
            base_assessment=fixture.base_assessment,
            coaching_turn_plan=fixture.coaching_turn_plan,
        )

    async def coach_text(self, _command):
        fixture = InternalTextCoachingResponse.model_validate(
            load_fixture("text-coaching-response.json")
        )
        return fixture.coaching_turn_plan


class InternalApiTests(unittest.TestCase):
    def setUp(self) -> None:
        internal_app.dependency_overrides[get_settings] = make_settings
        internal_app.dependency_overrides[get_internal_service] = FakeInternalService
        self.client = TestClient(internal_app, raise_server_exceptions=False)

    def tearDown(self) -> None:
        internal_app.dependency_overrides.clear()

    def test_health_reports_ready_without_exposing_configuration(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"service": "ai-processing", "status": "ready", "model_configured": True},
        )

    def test_analysis_contract_fixture_round_trips(self) -> None:
        response = self.client.post(
            "/v1/analyses",
            json=load_fixture("analysis-request.json"),
            headers=authorization_header(),
        )

        self.assertEqual(response.status_code, 200)
        InternalAnalysisResponse.model_validate(response.json())
        self.assertEqual(response.json(), load_fixture("analysis-response.json"))

    def test_text_coaching_contract_fixture_round_trips(self) -> None:
        response = self.client.post(
            "/v1/coaching/text",
            json=load_fixture("text-coaching-request.json"),
            headers=authorization_header(),
        )

        self.assertEqual(response.status_code, 200)
        InternalTextCoachingResponse.model_validate(response.json())
        self.assertEqual(response.json(), load_fixture("text-coaching-response.json"))

    def test_internal_endpoint_rejects_missing_bearer(self) -> None:
        response = self.client.post(
            "/v1/coaching/text",
            json=load_fixture("text-coaching-request.json"),
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "INTERNAL_AUTH_FAILED")
        self.assertNotIn("internal-test-token", response.text)

    def test_validation_error_uses_internal_error_contract(self) -> None:
        response = self.client.post(
            "/v1/coaching/text",
            json={},
            headers=authorization_header(),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "ANALYSIS_CONTRACT_FAILED")

    def test_rejects_unexpected_interaction_meta_field(self) -> None:
        payload = copy.deepcopy(load_fixture("text-coaching-request.json"))
        payload["context_packet"]["recent_dialogue"].append(
            {
                "role": "assistant",
                "content": "좋아.",
                "interaction_meta": {"unexpected": "accepted"},
            }
        )

        response = self.client.post(
            "/v1/coaching/text",
            json=payload,
            headers=authorization_header(),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "ANALYSIS_CONTRACT_FAILED")

    def test_rejects_invalid_interaction_meta_response_mode(self) -> None:
        payload = copy.deepcopy(load_fixture("text-coaching-request.json"))
        payload["context_packet"]["recent_dialogue"].append(
            {
                "role": "assistant",
                "content": "좋아.",
                "interaction_meta": {
                    "response_mode": "verbose",
                    "positive_topic": None,
                    "question_topic": None,
                    "invite_mode": "none",
                },
            }
        )

        response = self.client.post(
            "/v1/coaching/text",
            json=payload,
            headers=authorization_header(),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "ANALYSIS_CONTRACT_FAILED")

    def test_rejects_invalid_interaction_meta_invite_mode(self) -> None:
        payload = copy.deepcopy(load_fixture("text-coaching-request.json"))
        payload["context_packet"]["recent_dialogue"].append(
            {
                "role": "assistant",
                "content": "좋아.",
                "interaction_meta": {
                    "response_mode": "short",
                    "positive_topic": None,
                    "question_topic": None,
                    "invite_mode": "bad_mode",
                },
            }
        )

        response = self.client.post(
            "/v1/coaching/text",
            json=payload,
            headers=authorization_header(),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "ANALYSIS_CONTRACT_FAILED")

    def test_rejects_duplicate_source_episode_ids(self) -> None:
        payload = copy.deepcopy(load_fixture("text-coaching-request.json"))
        episode_id = "22222222-2222-4222-8222-222222222222"
        payload["context_packet"]["relevant_user_context_facts"].append(
            {
                "fact_id": "11111111-1111-4111-8111-111111111111",
                "version": 1,
                "statement": "오른손잡이다.",
                "evidence_level": "USER_REPORTED",
                "scope": {
                    "shot_profile": "full_swing",
                    "club": "7번 아이언",
                    "club_group": None,
                    "short_game_type": None,
                },
                "source_episode_ids": [episode_id, episode_id],
            }
        )

        response = self.client.post(
            "/v1/coaching/text",
            json=payload,
            headers=authorization_header(),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "ANALYSIS_CONTRACT_FAILED")

    def test_rejects_analysis_request_without_media_presence(self) -> None:
        payload = copy.deepcopy(load_fixture("analysis-request.json"))
        payload["context_packet"]["request_context"]["media_presence"] = False

        response = self.client.post(
            "/v1/analyses",
            json=payload,
            headers=authorization_header(),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "ANALYSIS_CONTRACT_FAILED")

    def test_rejects_text_request_with_media_presence(self) -> None:
        payload = copy.deepcopy(load_fixture("text-coaching-request.json"))
        payload["context_packet"]["request_context"]["media_presence"] = True

        response = self.client.post(
            "/v1/coaching/text",
            json=payload,
            headers=authorization_header(),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "ANALYSIS_CONTRACT_FAILED")


if __name__ == "__main__":
    unittest.main()
