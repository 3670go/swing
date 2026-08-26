import unittest
from pathlib import Path
from typing import Any

from app.domain.models import CoachContent, ObservationItem, ShotContext, VisionObservation
from app.graphs.runtime import (
    GraphContractError,
    build_analysis_content_graph,
    build_text_content_graph,
)


def make_context() -> ShotContext:
    return ShotContext(
        shot_profile="full_swing",
        club="7번 아이언",
        camera_view="face_on",
        handedness="right",
        analysis_goal="posture_correction",
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


def make_text_content() -> CoachContent:
    return CoachContent(
        evidence_mode="text_only",
        direct_answer="먼저 반복해서 무너지는 한 가지를 찾아야 해.",
        causal_chain=["한 번에 여러 동작을 바꾸면 원인을 구분하기 어렵다."],
        evidence_boundary="현재 대화에서 확인된 내용만 사용함",
        cannot_determine=[],
        observation_indexes=[],
        single_change="최근 가장 자주 나온 미스 하나를 정한다.",
        verification="같은 클럽으로 다섯 번 쳐서 반복 여부를 본다.",
    )


class FakeModel:
    def __init__(
        self,
        observation: VisionObservation,
        *,
        invalid_media_content: bool = False,
    ) -> None:
        self.observation = observation
        self.invalid_media_content = invalid_media_content
        self.observe_values: dict[str, Any] | None = None
        self.compose_question: str | None = None
        self.last_policy: dict[str, Any] | None = None

    async def observe(self, **values: Any) -> VisionObservation:
        self.observe_values = values
        return self.observation

    async def compose_media_content(self, **values: Any) -> CoachContent:
        self.compose_question = values["question"]
        assessment = values["base_assessment"]
        return CoachContent(
            evidence_mode=(
                "text_only"
                if self.invalid_media_content
                else ("photo_limited" if values["media_kind"] == "photo" else "video_ready")
            ),
            direct_answer="손과 몸통 사이 공간을 먼저 확인해야 해.",
            causal_chain=["손이 오른쪽 골반 옆에 위치함"],
            evidence_boundary="선택된 영상 프레임",
            cannot_determine=[
                "Club Path 수치",
                *(
                    ["사진 한 장으로 동작 순서와 템포는 판단 불가"]
                    if values["media_kind"] == "photo"
                    else []
                ),
            ],
            observation_indexes=[] if self.invalid_media_content else [0],
            base_assessment_hash=(
                None if self.invalid_media_content else assessment.assessment_hash
            ),
            single_change="손이 오른쪽 허벅지 앞 공간으로 오는지만 확인한다.",
            verification="같은 각도에서 다시 촬영한다.",
        )

    async def compose_text_content(self, **values: Any) -> CoachContent:
        self.last_policy = values["policy"]
        return make_text_content()


class GraphRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_content_graph_returns_internal_content_only(self) -> None:
        model = FakeModel(make_observation())

        result = await build_text_content_graph(model).ainvoke(  # type: ignore[arg-type]
            {
                "message": "자꾸 당겨 치는 느낌이야",
                "context": make_context(),
                "history": [],
                "latest_analysis": None,
            }
        )

        self.assertEqual(result["content"].evidence_mode, "text_only")
        self.assertNotIn("reply", result)
        self.assertEqual(model.last_policy["response_mode"], "short")

    async def test_analysis_observation_is_blind_to_question_and_feel(self) -> None:
        model = FakeModel(make_observation())

        result = await build_analysis_content_graph(model).ainvoke(  # type: ignore[arg-type]
            {
                "frame_paths": [Path("frame.jpg")],
                "media_kind": "video",
                "context": make_context(),
                "question": "왼쪽으로 밀리는 느낌이야",
                "history": [],
            }
        )

        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["content"].evidence_mode, "video_ready")
        self.assertNotIn("question", model.observe_values)
        self.assertNotIn("feel", model.observe_values)
        self.assertEqual(model.compose_question, "왼쪽으로 밀리는 느낌이야")

    async def test_photo_analysis_is_limited(self) -> None:
        model = FakeModel(make_observation())

        result = await build_analysis_content_graph(model).ainvoke(  # type: ignore[arg-type]
            {
                "frame_paths": [Path("frame.jpg")],
                "media_kind": "photo",
                "context": make_context(),
                "question": "봐줘",
                "history": [],
            }
        )

        self.assertEqual(result["status"], "limited")
        self.assertEqual(result["content"].evidence_mode, "photo_limited")

    async def test_non_golf_media_is_rejected_before_content_generation(self) -> None:
        model = FakeModel(make_observation(is_golf_media=False))

        result = await build_analysis_content_graph(model).ainvoke(  # type: ignore[arg-type]
            {
                "frame_paths": [Path("frame.jpg")],
                "media_kind": "video",
                "context": make_context(),
                "question": "봐줘",
                "history": [],
            }
        )

        self.assertEqual(result["status"], "rejected")
        self.assertNotIn("content", result)

    async def test_media_content_cannot_downgrade_to_text_only_evidence(self) -> None:
        model = FakeModel(make_observation(), invalid_media_content=True)

        with self.assertRaises(GraphContractError):
            await build_analysis_content_graph(model).ainvoke(  # type: ignore[arg-type]
                {
                    "frame_paths": [Path("frame.jpg")],
                    "media_kind": "video",
                    "context": make_context(),
                    "question": "봐줘",
                    "history": [],
                }
            )


if __name__ == "__main__":
    unittest.main()
