import asyncio
import unittest
import uuid
from contextlib import contextmanager
from io import BytesIO
from types import SimpleNamespace
from typing import Any

from fastapi import UploadFile
from starlette.datastructures import Headers

from app.config import Settings
from app.domain.models import (
    AssessmentFinding,
    BaseAssessment,
    CoachContent,
    CoachReply,
    ConversationReply,
    ObservationItem,
    ShotContext,
    VisionObservation,
)
from app.ports.swing_analyzer import SwingAnalysisInput, SwingAnalysisResult
from app.services.swing_analysis import StartSwingAnalysisUseCase


class FakeDatabase:
    @contextmanager
    def session(self) -> Any:
        yield object()


class FakeOwnerConversations:
    owner_id = uuid.uuid4()
    conversation_id = uuid.uuid4()

    def get_or_create_owner(self, session: Any, owner_hash: str) -> SimpleNamespace:
        return SimpleNamespace(id=self.owner_id)

    def get_or_create_conversation(self, session: Any, **values: Any) -> SimpleNamespace:
        return SimpleNamespace(id=self.conversation_id)


class FakeMessages:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    def add_message(self, session: Any, **values: Any) -> SimpleNamespace:
        self.created.append(values)
        return SimpleNamespace()

    def recent_messages(self, session: Any, conversation_id: uuid.UUID) -> list[dict[str, Any]]:
        return [{"role": "user", "content": "전체를 봐줘", "interaction_meta": None}]


class FakeAnalyses:
    swing_session_id = uuid.uuid4()
    run_id = uuid.uuid4()

    def __init__(self) -> None:
        self.uploaded: list[dict[str, Any]] = []
        self.finished: list[dict[str, Any]] = []

    def create_swing_session(self, session: Any, **values: Any) -> SimpleNamespace:
        return SimpleNamespace(id=self.swing_session_id)

    def create_analysis_run(self, session: Any, **values: Any) -> SimpleNamespace:
        return SimpleNamespace(id=self.run_id)

    def create_uploaded_media(self, session: Any, **values: Any) -> SimpleNamespace:
        self.uploaded.append(values)
        return SimpleNamespace()

    def finish_analysis(self, session: Any, **values: Any) -> None:
        self.finished.append(values)

    def fail_analysis(self, session: Any, run_id: uuid.UUID, error_code: str) -> None:
        raise AssertionError(f"Unexpected analysis failure: {error_code}")


class FakeMediaStore:
    def __init__(self) -> None:
        self.uploaded_paths: list[str] = []

    def upload(self, storage_path: str, source_path: Any, content_type: str) -> None:
        self.uploaded_paths.append(storage_path)

    def remove_many(self, storage_paths: list[str]) -> None:
        raise AssertionError(f"Unexpected storage rollback: {storage_paths}")


class FakeFrameExtractor:
    async def extract(self, video_path: Any, output_directory: Any, frame_count: int) -> list[Any]:
        raise AssertionError("Photo analysis must not invoke FFmpeg")


class FakeAnalyzer:
    is_configured = True

    async def analyze(self, analysis_input: SwingAnalysisInput) -> SwingAnalysisResult:
        observation = VisionObservation(
            is_golf_media=True,
            golf_media_reason="골프 스윙 어드레스가 보입니다.",
            observations=[
                ObservationItem(
                    subject="손",
                    reference="오른쪽 골반",
                    phase="다운스윙",
                    state="손이 오른쪽 골반 옆에 있습니다.",
                    assessment_category="arm_body_space",
                    confidence=0.8,
                )
            ],
            cannot_determine=["클럽 패스 수치"],
        )
        assessment_hash = "a" * 64
        reply = CoachReply(
            base_assessment=BaseAssessment(
                primary_category="arm_body_space",
                importance="medium",
                findings=[
                    AssessmentFinding(
                        category="arm_body_space",
                        observation_indexes=[0],
                        summary="손이 오른쪽 골반 옆에 있습니다.",
                        confidence=0.8,
                    )
                ],
                cannot_determine=["클럽 패스 수치"],
                assessment_hash=assessment_hash,
            ),
            content=CoachContent(
                evidence_mode="photo_limited",
                direct_answer="손 위치를 먼저 확인합니다.",
                causal_chain=[],
                evidence_boundary="사진으로 동작 순서와 전환은 판단할 수 없습니다.",
                cannot_determine=["템포"],
                observation_indexes=[0],
                base_assessment_hash=assessment_hash,
            ),
            conversation=ConversationReply(message="손 위치를 먼저 확인해볼게."),
        )
        return SwingAnalysisResult(
            status="limited",
            observation=observation,
            reply=reply,
            interaction_meta={"invite_mode": "none"},
        )


def make_settings() -> Settings:
    return Settings(
        database_url="postgresql://user:password@host:5432/postgres",
        supabase_url="https://project.supabase.co",
        supabase_secret_key="example-secret",
        gemini_api_key="example-gemini-key",
    )


class StartSwingAnalysisUseCaseTests(unittest.TestCase):
    def test_photo_analysis_happy_path_crosses_all_application_boundaries(self) -> None:
        owner_conversations = FakeOwnerConversations()
        messages = FakeMessages()
        analyses = FakeAnalyses()
        media_store = FakeMediaStore()
        use_case = StartSwingAnalysisUseCase(
            settings=make_settings(),
            database=FakeDatabase(),  # type: ignore[arg-type]
            owner_conversations=owner_conversations,  # type: ignore[arg-type]
            messages=messages,  # type: ignore[arg-type]
            analyses=analyses,  # type: ignore[arg-type]
            media_store=media_store,  # type: ignore[arg-type]
            analyzer=FakeAnalyzer(),
            frame_extractor=FakeFrameExtractor(),
        )
        upload = UploadFile(
            file=BytesIO(b"fake-jpeg"),
            filename="swing.jpg",
            headers=Headers({"content-type": "image/jpeg"}),
        )

        result = asyncio.run(
            use_case.execute(
                files=[upload],
                anonymous_session_hash="hashed-owner",
                context=ShotContext(
                    shot_profile="full_swing",
                    club="7번 아이언",
                    camera_view="down_the_line",
                    handedness="right",
                    analysis_goal="posture_correction",
                ),
                question="전체를 봐줘",
                conversation_id=None,
            )
        )

        self.assertEqual(result.status, "limited")
        self.assertEqual(result.analysis_run_id, analyses.run_id)
        self.assertEqual(len(analyses.uploaded), 1)
        self.assertEqual(len(analyses.finished), 1)
        self.assertEqual([message["role"] for message in messages.created], ["user", "assistant"])
        self.assertEqual(len(media_store.uploaded_paths), 1)


if __name__ == "__main__":
    unittest.main()
