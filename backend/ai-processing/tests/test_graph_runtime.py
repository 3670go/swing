import unittest
from pathlib import Path
from typing import Any

from app.domain.models import (
    CoachContent,
    ConversationReply,
    ObservationItem,
    ShotContext,
    VisionObservation,
)
from app.graphs.runtime import (
    GraphContractError,
    build_analysis_graph,
    build_base_assessment,
    build_text_graph,
)

CONVERSATION_FIXTURES = (
    {
        "message": "골프 잘 치고 싶엉",
        "reply": "좋아. 우선 자주 무너지는 한 가지부터 찾아서 줄이면 돼.",
        "context_relevant": False,
    },
    {
        "message": "나 매킬로이처럼 치고 싶은데",
        "reply": "그 스윙 전체를 복사하기보다 원하는 특징 하나부터 네 동작과 맞춰보자.",
        "context_relevant": False,
    },
    {
        "message": "다운스윙 영상에서 손 위치가 왜 저래",
        "reply": "손 위치만 떼어 보기보다 그 직전에 몸통과 팔 사이 공간이 어떻게 바뀌는지 봐야 해.",
        "context_relevant": True,
    },
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
        conversation: ConversationReply | None = None,
        photo_boundary: bool = False,
        preserve: bool = False,
    ) -> None:
        self.observation = observation
        self.conversation = conversation or ConversationReply(
            message="영상에서는 손과 몸통 사이 공간을 먼저 봐야 해."
        )
        self.photo_boundary = photo_boundary
        self.preserve = preserve
        self.observe_values: dict[str, Any] | None = None
        self.compose_question: str | None = None
        self.compose_calls = 0
        self.writer_calls = 0
        self.last_policy: dict[str, Any] | None = None

    async def observe(self, **values: Any) -> VisionObservation:
        self.observe_values = values
        return self.observation

    async def compose_media_content(self, **values: Any) -> CoachContent:
        self.compose_calls += 1
        self.compose_question = values["question"]
        assessment = values["base_assessment"]
        cannot_determine = ["Club Path 수치"]
        if self.photo_boundary:
            cannot_determine.append("동작 순서와 템포")
        return CoachContent(
            evidence_mode=("photo_limited" if values["media_kind"] == "photo" else "video_ready"),
            direct_answer="손과 몸통 사이 공간을 먼저 확인해야 해.",
            causal_chain=["손이 오른쪽 골반 옆에 위치함"],
            evidence_boundary="사진은 전환을 확정하지 않음"
            if self.photo_boundary
            else "영상 프레임",
            cannot_determine=cannot_determine,
            observation_indexes=[0],
            base_assessment_hash=assessment.assessment_hash,
            single_change="손이 오른쪽 허벅지 앞 공간으로 오는지만 확인한다.",
            verification="같은 각도에서 다시 촬영한다.",
            preserve_candidate=("팔과 헤드가 막히지 않은 점은 유지해." if self.preserve else None),
            preserve_topic="arm_head_release" if self.preserve else None,
        )

    async def compose_text_content(self, **values: Any) -> CoachContent:
        self.last_policy = values["policy"]
        return make_text_content()

    async def write_conversation(self, **values: Any) -> ConversationReply:
        self.writer_calls += 1
        return self.conversation


class GraphRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_blind_observation_excludes_question_and_feel(self) -> None:
        model = FakeModel(make_observation())
        graph = build_analysis_graph(model)  # type: ignore[arg-type]

        result = await graph.ainvoke(
            {
                "frame_paths": [Path("frame.jpg")],
                "media_kind": "video",
                "context": make_context(),
                "question": "왼쪽으로 밀리는 느낌이야",
                "history": [],
            }
        )

        self.assertEqual(result["status"], "succeeded")
        self.assertNotIn("question", model.observe_values or {})
        self.assertNotIn("feel", model.observe_values or {})
        self.assertEqual(model.compose_question, "왼쪽으로 밀리는 느낌이야")

    async def test_same_observation_freezes_same_assessment_for_different_questions(self) -> None:
        hashes = []
        for question in ("왼쪽으로 밀리는 느낌이야", "팔이 너무 붙는 것 같아"):
            model = FakeModel(make_observation())
            result = await build_analysis_graph(model).ainvoke(  # type: ignore[arg-type]
                {
                    "frame_paths": [Path("frame.jpg")],
                    "media_kind": "video",
                    "context": make_context(),
                    "question": question,
                    "history": [],
                }
            )
            hashes.append(result["reply"].base_assessment.assessment_hash)

        self.assertEqual(hashes[0], hashes[1])

    def test_domain_priority_is_fixed_independent_of_observation_order(self) -> None:
        observation = make_observation()
        observation.observations.insert(
            0,
            ObservationItem(
                timestamp="frame_01",
                subject="팔",
                reference="몸통",
                phase="백스윙 탑",
                state="팔이 몸통 오른쪽에 위치함",
                assessment_category="backswing",
                confidence=0.9,
            ),
        )
        observation.observations.append(
            ObservationItem(
                timestamp="frame_05",
                subject="골반",
                reference="공",
                phase="임팩트",
                state="골반 중심이 공보다 왼쪽에 위치함",
                assessment_category="impact_structure",
                confidence=0.7,
            )
        )

        assessment = build_base_assessment(observation)

        self.assertEqual(assessment.primary_category, "impact_structure")
        self.assertEqual(assessment.importance, "high")
        self.assertEqual(assessment.findings[0].category, "impact_structure")

    async def test_non_golf_media_never_composes_coaching_content(self) -> None:
        model = FakeModel(make_observation(is_golf_media=False))
        graph = build_analysis_graph(model)  # type: ignore[arg-type]

        result = await graph.ainvoke(
            {
                "frame_paths": [Path("frame.jpg")],
                "media_kind": "video",
                "context": make_context(),
                "question": "분석해줘",
                "history": [],
            }
        )

        self.assertEqual(result["status"], "rejected")
        self.assertIsNone(result["reply"])
        self.assertEqual(model.compose_calls, 0)
        self.assertEqual(model.writer_calls, 0)

    async def test_photo_requires_motion_sequence_limit(self) -> None:
        model = FakeModel(make_observation(), photo_boundary=True)
        result = await build_analysis_graph(model).ainvoke(  # type: ignore[arg-type]
            {
                "frame_paths": [Path("photo.jpg")],
                "media_kind": "photo",
                "context": make_context(),
                "question": "어때?",
                "history": [],
            }
        )

        self.assertEqual(result["status"], "limited")

    async def test_observation_rejects_measurement_claim(self) -> None:
        observation = make_observation()
        observation.observations[0].state = "Club Path는 +3°임"
        model = FakeModel(observation)

        with self.assertRaises(GraphContractError):
            await build_analysis_graph(model).ainvoke(  # type: ignore[arg-type]
                {
                    "frame_paths": [Path("frame.jpg")],
                    "media_kind": "video",
                    "context": make_context(),
                    "question": "분석해줘",
                    "history": [],
                }
            )

    async def test_media_graph_applies_question_and_positive_cadence(self) -> None:
        model = FakeModel(
            make_observation(),
            preserve=True,
            conversation=ConversationReply(
                message="손과 몸통 사이 공간을 먼저 봐야 해.",
                positive_feedback="팔과 헤드가 막히지 않은 점은 유지해.",
                positive_topic="arm_head_release",
                follow_up_question="잘 맞은 샷에서는 몸 느낌부터 달랐어?",
                question_topic="good_bad_feel",
                invite_mode="compare_good_bad",
            ),
        )
        history = [
            {
                "role": "assistant",
                "content": "첫 질문",
                "interaction_meta": {
                    "question_topic": "timing",
                    "positive_topic": "arm_head_release",
                },
            },
            {
                "role": "assistant",
                "content": "두 번째 질문",
                "interaction_meta": {"question_topic": "shot_result"},
            },
        ]

        result = await build_analysis_graph(model).ainvoke(  # type: ignore[arg-type]
            {
                "frame_paths": [Path("frame.jpg")],
                "media_kind": "video",
                "context": make_context(),
                "question": "이번 영상은 어때?",
                "history": history,
            }
        )

        conversation = result["reply"].conversation
        self.assertIsNone(conversation.follow_up_question)
        self.assertIsNone(conversation.positive_feedback)
        self.assertIsNone(result["interaction_meta"]["question_topic"])
        self.assertIsNone(result["interaction_meta"]["positive_topic"])

    async def test_surface_guard_replaces_internal_contract_language(self) -> None:
        model = FakeModel(
            make_observation(),
            conversation=ConversationReply(message="OBSERVATION 목록부터 설명합니다."),
        )
        result = await build_text_graph(model).ainvoke(  # type: ignore[arg-type]
            {
                "message": "골프 잘 치고 싶엉",
                "context": make_context(),
                "history": [],
                "latest_analysis": None,
            }
        )

        self.assertEqual(result["reply"].message, make_text_content().direct_answer)

    async def test_conversation_fixtures_keep_default_context_out_of_casual_chat(self) -> None:
        for fixture in CONVERSATION_FIXTURES:
            with self.subTest(message=fixture["message"]):
                model = FakeModel(
                    make_observation(),
                    conversation=ConversationReply(message=fixture["reply"]),
                )
                result = await build_text_graph(model).ainvoke(  # type: ignore[arg-type]
                    {
                        "message": fixture["message"],
                        "context": make_context(),
                        "history": [],
                        "latest_analysis": None,
                    }
                )

                self.assertEqual(result["reply"].message, fixture["reply"])
                self.assertEqual(model.last_policy["context_relevant"], fixture["context_relevant"])
                self.assertNotIn("현재 조건", result["reply"].message)
                self.assertNotIn("7번 아이언", result["reply"].message)

    async def test_text_graph_drops_third_consecutive_follow_up_question(self) -> None:
        model = FakeModel(
            make_observation(),
            conversation=ConversationReply(
                message="출발 방향부터 구분해보자.",
                follow_up_question="잘된 샷과 안 된 샷은 뭐가 달랐어?",
                question_topic="good_bad_difference",
                invite_mode="compare_good_bad",
            ),
        )
        history = [
            {
                "role": "assistant",
                "content": "첫 질문",
                "interaction_meta": {"question_topic": "timing"},
            },
            {"role": "user", "content": "전환 때", "interaction_meta": None},
            {
                "role": "assistant",
                "content": "두 번째 질문",
                "interaction_meta": {"question_topic": "shot_result"},
            },
        ]

        result = await build_text_graph(model).ainvoke(  # type: ignore[arg-type]
            {
                "message": "왼쪽으로 가",
                "context": make_context(),
                "history": history,
                "latest_analysis": None,
            }
        )

        self.assertIsNone(result["reply"].follow_up_question)
        self.assertIsNone(result["reply"].question_topic)
        self.assertEqual(result["reply"].invite_mode, "none")


if __name__ == "__main__":
    unittest.main()
