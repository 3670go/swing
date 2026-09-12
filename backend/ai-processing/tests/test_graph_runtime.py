import unittest
from pathlib import Path
from typing import Any
from uuid import UUID

from app.domain.analysis_policy import build_base_assessment
from app.domain.models import (
    CoachContent,
    CoachingTurnPlan,
    ContextPacket,
    ObservationItem,
    OpenLoopCandidate,
    ProgressCandidate,
    RecognitionCandidate,
    RoadmapUpdateCandidate,
    ShotContext,
    VisionObservation,
)
from app.graphs.coaching_guards import (
    CoachingGuardViolation,
    validate_media_turn_plan,
    validate_text_turn_plan,
)
from app.graphs.runtime import (
    GraphContractError,
    build_analysis_content_graph,
    build_text_content_graph,
)


def make_text_coach_content() -> CoachContent:
    return CoachContent(
        evidence_mode="text_only",
        direct_answer="반복되는 미스 하나부터 줄이면 돼.",
        causal_chain=["여러 동작을 동시에 바꾸면 원인 구분이 어렵다."],
        evidence_boundary="현재 대화 근거",
        cannot_determine=[],
        observation_indexes=[],
        base_assessment_hash=None,
        single_change="가장 잦은 미스 하나를 정한다.",
        verification="같은 클럽으로 다섯 번 확인한다.",
    )


def make_context() -> ShotContext:
    return ShotContext(
        shot_profile="full_swing",
        club="7번 아이언",
        camera_view="face_on",
        handedness="right",
        analysis_goal="posture_correction",
    )


def make_context_packet(
    *,
    media_presence: bool = False,
    user_message: str = "자꾸 당겨쳐",
) -> ContextPacket:
    return ContextPacket.model_validate(
        {
            "context_snapshot_id": "88888888-8888-4888-8888-888888888888",
            "context_snapshot_version": 1,
            "request_context": {
                "user_message": user_message,
                "user_feel": "몸이 먼저 도는 느낌",
                "selected_shot_context": make_context().model_dump(mode="json"),
                "media_presence": media_presence,
            },
            "active_coaching_topic": None,
            "roadmap_context": None,
            "recent_dialogue": [],
            "relevant_analysis_episodes": [],
            "relevant_user_context_facts": [],
            "pending_open_loop": None,
            "recognition_context": {
                "unrecognized_progress_events": [],
                "recently_recognized_topics": [],
                "last_roadmap_reveal_at": None,
            },
        }
    )


def make_observation(*, is_golf_media: bool = True) -> VisionObservation:
    observations = []
    if is_golf_media:
        observations = [
            ObservationItem(
                timestamp="frame_03",
                subject="손",
                reference="오른쪽 골반",
                phase="다운스윙",
                state="손이 오른쪽 골반 옆에 위치함",
                assessment_category="arm_body_space",
                confidence=0.8,
            )
        ]
    return VisionObservation(
        is_golf_media=is_golf_media,
        golf_media_reason="골퍼와 클럽이 보임" if is_golf_media else "골프 장면이 보이지 않음",
        observations=observations,
        cannot_determine=["Club Path와 Face Angle은 2D 영상만으로 판단 불가"],
    )


def make_plan(
    *,
    evidence_mode: str = "text_only",
    assessment_hash: str | None = None,
    progress_level: str | None = None,
    recognition_intensity: str | None = None,
) -> CoachingTurnPlan:
    progress = None
    recognition = None
    if progress_level is not None:
        progress = ProgressCandidate(
            target_milestone_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
            expected_version=1,
            progress_level=progress_level,  # type: ignore[arg-type]
            user_signal="세 번 연속 결과가 좋아졌다.",
            evidence_references=[{"source_type": "MESSAGE", "source_id": "current-user-message"}],
        )
    if recognition_intensity is not None:
        recognition = RecognitionCandidate(
            target="전환 공간 실험",
            proposed_intensity=recognition_intensity,  # type: ignore[arg-type]
            recognition_content="반복 결과를 만든 점이 핵심입니다.",
        )
    return CoachingTurnPlan(
        coach_content=CoachContent(
            evidence_mode=evidence_mode,  # type: ignore[arg-type]
            direct_answer="손과 몸통 사이 공간을 먼저 확인해야 해.",
            causal_chain=["손이 오른쪽 골반 옆에 위치함"],
            evidence_boundary=(
                "사진 한 장으로 동작 순서와 템포는 판단 불가"
                if evidence_mode == "photo_limited"
                else "선택된 영상 프레임"
                if evidence_mode == "video_ready"
                else "현재 대화 근거"
            ),
            cannot_determine=(
                ["Club Path 수치", "사진 한 장으로 동작 순서와 템포는 판단 불가"]
                if evidence_mode == "photo_limited"
                else ["Club Path 수치"]
            ),
            observation_indexes=[] if evidence_mode == "text_only" else [0],
            base_assessment_hash=None if evidence_mode == "text_only" else assessment_hash,
            single_change="손이 오른쪽 허벅지 앞 공간으로 오는지만 확인한다.",
            verification="같은 각도에서 다시 촬영한다.",
        ),
        problem_reframe_candidate=None,
        coaching_topic_candidate=None,
        roadmap_update_candidates=[],
        progress_candidate=progress,
        recognition_candidate=recognition,
        open_loop_candidate=OpenLoopCandidate(
            carry_forward_feel="손이 먼저 내려오는 느낌",
            next_single_change="현재 감각을 유지한다.",
            next_verification="같은 후방 영상에서 확인한다.",
            completion_condition="영상에서도 전환 공간이 확인된다.",
            predicted_result="당김이 줄어든다.",
            question="다음 영상은 언제 올릴 수 있어?",
        ),
    )


class FakeModel:
    is_configured = True

    def __init__(
        self,
        observation: VisionObservation,
        *,
        invalid_media_content: bool = False,
        progress_level: str | None = None,
        recognition_intensity: str | None = None,
    ) -> None:
        self.observation = observation
        self.invalid_media_content = invalid_media_content
        self.progress_level = progress_level
        self.recognition_intensity = recognition_intensity
        self.observe_values: dict[str, Any] = {}
        self.plan_values: dict[str, Any] = {}
        self.text_values: dict[str, Any] = {}
        self.observe_calls = 0
        self.plan_calls = 0
        self.text_calls = 0

    async def observe(self, **values: Any) -> VisionObservation:
        self.observe_calls += 1
        self.observe_values = values
        return self.observation

    async def compose_text_coach_content(self, **values: Any) -> CoachContent:
        self.text_calls += 1
        self.text_values = values
        return make_text_coach_content()

    async def compose_media_content(self, **values: Any) -> CoachContent:
        self.plan_calls += 1
        self.plan_values = values
        assessment = values.get("base_assessment")
        media_kind = values.get("media_kind")
        evidence_mode = "photo_limited" if media_kind == "photo" else "video_ready"
        if self.invalid_media_content:
            evidence_mode = "text_only"
        return make_plan(
            evidence_mode=evidence_mode,
            assessment_hash=None if assessment is None else assessment.assessment_hash,
            progress_level=self.progress_level,
            recognition_intensity=self.recognition_intensity,
        ).coach_content

    async def compose_coaching_turn_plan(self, **values: Any) -> CoachingTurnPlan:
        self.plan_calls += 1
        self.plan_values = values
        assessment = values.get("base_assessment")
        media_kind = values.get("media_kind")
        if media_kind is None:
            return make_plan(
                evidence_mode="text_only",
                progress_level=self.progress_level,
                recognition_intensity=self.recognition_intensity,
            )
        evidence_mode = "photo_limited" if media_kind == "photo" else "video_ready"
        if self.invalid_media_content:
            evidence_mode = "text_only"
        return make_plan(
            evidence_mode=evidence_mode,
            assessment_hash=None if assessment is None else assessment.assessment_hash,
            progress_level=self.progress_level,
            recognition_intensity=self.recognition_intensity,
        )


class GraphRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_content_graph_returns_coaching_turn_plan(
        self,
    ) -> None:
        model = FakeModel(make_observation())

        result = await build_text_content_graph(model).ainvoke(  # type: ignore[arg-type]
            {
                "context_packet": make_context_packet(),
            }
        )

        plan = result["coaching_turn_plan"]
        self.assertEqual(plan.coach_content.evidence_mode, "text_only")
        # Text turn generates only CoachContent; Python owns the empty state candidates.
        self.assertEqual(plan.roadmap_update_candidates, [])
        self.assertIsNone(plan.problem_reframe_candidate)
        self.assertIsNone(plan.coaching_topic_candidate)
        self.assertIsNone(plan.progress_candidate)
        self.assertIsNone(plan.recognition_candidate)
        self.assertIsNone(plan.open_loop_candidate)
        self.assertEqual(model.observe_calls, 0)
        self.assertEqual(model.text_calls, 1)
        self.assertEqual(model.plan_calls, 0)

    async def test_analysis_observation_is_blind_to_question_and_feel(self) -> None:
        model = FakeModel(make_observation())
        context_packet = make_context_packet(media_presence=True)

        result = await build_analysis_content_graph(model).ainvoke(  # type: ignore[arg-type]
            {
                "frame_paths": [Path("frame.jpg")],
                "media_kind": "video",
                "context_packet": context_packet,
            }
        )

        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["coaching_turn_plan"].coach_content.evidence_mode, "video_ready")
        self.assertEqual(
            set(model.observe_values),
            {"frame_paths", "media_kind", "shot_profile", "camera_view", "handedness"},
        )
        self.assertNotIn("context_packet", model.observe_values)
        self.assertNotIn("user_message", model.observe_values)
        self.assertNotIn("user_feel", model.observe_values)
        self.assertNotIn("shot_result", model.observe_values)
        self.assertEqual(model.observe_calls, 1)
        self.assertEqual(model.plan_calls, 1)
        self.assertEqual(model.plan_values["question"], context_packet.request_context.user_message)

    async def test_analysis_observation_input_ignores_malicious_feel_changes(self) -> None:
        first_model = FakeModel(make_observation())
        first_packet = make_context_packet(media_presence=True, user_message="정상 질문")

        await build_analysis_content_graph(first_model).ainvoke(  # type: ignore[arg-type]
            {
                "frame_paths": [Path("frame.jpg")],
                "media_kind": "video",
                "context_packet": first_packet,
            }
        )

        second_model = FakeModel(make_observation())
        second_packet = make_context_packet(media_presence=True, user_message="허리 느낌이 완벽해")
        second_packet.request_context.user_feel = "일부러 바꾼 강한 FEEL"
        second_packet.request_context.selected_shot_context.shot_result = "완벽한 드로우"

        await build_analysis_content_graph(second_model).ainvoke(  # type: ignore[arg-type]
            {
                "frame_paths": [Path("frame.jpg")],
                "media_kind": "video",
                "context_packet": second_packet,
            }
        )

        first_observation_input = {
            key: value for key, value in first_model.observe_values.items() if key != "frame_paths"
        }
        second_observation_input = {
            key: value for key, value in second_model.observe_values.items() if key != "frame_paths"
        }
        self.assertEqual(first_observation_input, second_observation_input)

    async def test_photo_analysis_is_limited(self) -> None:
        model = FakeModel(make_observation())

        result = await build_analysis_content_graph(model).ainvoke(  # type: ignore[arg-type]
            {
                "frame_paths": [Path("frame.jpg")],
                "media_kind": "photo",
                "context_packet": make_context_packet(media_presence=True),
            }
        )

        self.assertEqual(result["status"], "limited")
        self.assertEqual(result["coaching_turn_plan"].coach_content.evidence_mode, "photo_limited")

    async def test_non_golf_media_is_rejected_before_plan_generation(self) -> None:
        model = FakeModel(make_observation(is_golf_media=False))

        result = await build_analysis_content_graph(model).ainvoke(  # type: ignore[arg-type]
            {
                "frame_paths": [Path("frame.jpg")],
                "media_kind": "video",
                "context_packet": make_context_packet(media_presence=True),
            }
        )

        self.assertEqual(result["status"], "rejected")
        self.assertNotIn("coaching_turn_plan", result)
        self.assertEqual(model.plan_calls, 0)

    async def test_media_content_cannot_downgrade_to_text_only_evidence(self) -> None:
        model = FakeModel(make_observation(), invalid_media_content=True)

        with self.assertRaises(GraphContractError):
            await build_analysis_content_graph(model).ainvoke(  # type: ignore[arg-type]
                {
                    "frame_paths": [Path("frame.jpg")],
                    "media_kind": "video",
                    "context_packet": make_context_packet(media_presence=True),
                }
            )

    def test_text_message_cannot_create_video_verified_progress(self) -> None:
        plan = make_plan(evidence_mode="text_only", progress_level="VIDEO_VERIFIED_PROGRESS")

        with self.assertRaises(CoachingGuardViolation):
            validate_text_turn_plan(plan)

    def test_text_message_cannot_mark_video_verified_roadmap_progress(self) -> None:
        plan = make_plan(evidence_mode="text_only")
        plan.roadmap_update_candidates.append(
            RoadmapUpdateCandidate(
                target_type="MILESTONE",
                target_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
                expected_version=1,
                proposed_transition="MARK_VIDEO_VERIFIED_PROGRESS",
                proposed_content="영상에서도 좋아졌다.",
                evidence_references=[
                    {"source_type": "MESSAGE", "source_id": "current-user-message"}
                ],
            )
        )

        with self.assertRaises(CoachingGuardViolation):
            validate_text_turn_plan(plan)

    async def test_media_observation_can_create_video_verified_progress(self) -> None:
        observation = make_observation()
        assessment = build_base_assessment(observation)
        plan = make_plan(
            evidence_mode="video_ready",
            assessment_hash=assessment.assessment_hash,
            progress_level="VIDEO_VERIFIED_PROGRESS",
        )
        assert plan.progress_candidate is not None
        plan.progress_candidate.evidence_references = [
            {"source_type": "OBSERVATION", "source_id": "observation:0"}
        ]

        validate_media_turn_plan(
            plan,
            media_kind="video",
            assessment=assessment,
            observation=observation,
        )
        self.assertEqual(plan.progress_candidate.progress_level, "VIDEO_VERIFIED_PROGRESS")

    def test_message_only_progress_declaration_is_rejected(self) -> None:
        plan = make_plan(
            evidence_mode="text_only",
            progress_level="VIDEO_VERIFIED_PROGRESS",
            recognition_intensity="PROGRESS_DECLARATION",
        )

        with self.assertRaises(CoachingGuardViolation):
            validate_text_turn_plan(plan)

    def test_user_reported_progress_can_use_acknowledgement(self) -> None:
        plan = make_plan(
            evidence_mode="text_only",
            progress_level="USER_REPORTED_PROGRESS",
            recognition_intensity="ACKNOWLEDGEMENT",
        )

        # Allowed evidence/intensity combination must pass the text guard unchanged.
        validate_text_turn_plan(plan)
        self.assertEqual(plan.progress_candidate.progress_level, "USER_REPORTED_PROGRESS")
        self.assertEqual(plan.recognition_candidate.proposed_intensity, "ACKNOWLEDGEMENT")

    def test_high_recognition_requires_high_progress_evidence(self) -> None:
        plan = make_plan(
            evidence_mode="text_only",
            progress_level="USER_REPORTED_PROGRESS",
            recognition_intensity="PROGRESS_DECLARATION",
        )

        with self.assertRaises(CoachingGuardViolation):
            validate_text_turn_plan(plan)


if __name__ == "__main__":
    unittest.main()
