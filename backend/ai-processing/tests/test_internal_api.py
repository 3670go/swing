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


def make_settings() -> Settings:
    return Settings(
        database_url="postgresql://user:secret@host:6543/postgres",
        supabase_url="https://project.supabase.co",
        supabase_secret_key="server-secret-key",
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
            coach_content=fixture.coach_content,
        )

    async def coach_text(self, _command):
        fixture = InternalTextCoachingResponse.model_validate(
            load_fixture("text-coaching-response.json")
        )
        return fixture.coach_content


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
            headers={"Authorization": "Bearer internal-test-token"},
        )

        self.assertEqual(response.status_code, 200)
        InternalAnalysisResponse.model_validate(response.json())
        self.assertEqual(response.json(), load_fixture("analysis-response.json"))

    def test_text_coaching_contract_fixture_round_trips(self) -> None:
        response = self.client.post(
            "/v1/coaching/text",
            json=load_fixture("text-coaching-request.json"),
            headers={"Authorization": "Bearer internal-test-token"},
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
            headers={"Authorization": "Bearer internal-test-token"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "ANALYSIS_CONTRACT_FAILED")


if __name__ == "__main__":
    unittest.main()
