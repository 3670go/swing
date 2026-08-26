import unittest

from app.conversation_policy import build_conversation_policy, enforce_conversation_policy
from app.domain.models import CoachContent, ConversationReply


def make_content(*, preserve: bool = False) -> CoachContent:
    return CoachContent(
        evidence_mode="text_only",
        direct_answer="핵심 답변입니다.",
        causal_chain=[],
        evidence_boundary="현재 대화 근거",
        cannot_determine=[],
        observation_indexes=[],
        preserve_candidate="헤드 릴리스는 유지해야 합니다." if preserve else None,
        preserve_topic="head_release" if preserve else None,
    )


def assistant_meta(
    *,
    question_topic: str | None = None,
    positive_topic: str | None = None,
) -> dict[str, object]:
    return {
        "role": "assistant",
        "content": "답변",
        "interaction_meta": {
            "question_topic": question_topic,
            "positive_topic": positive_topic,
        },
    }


class ConversationPolicyTests(unittest.TestCase):
    def test_blocks_question_after_two_question_turns(self) -> None:
        policy = build_conversation_policy(
            message="계속 땡겨쳐",
            history=[
                assistant_meta(question_topic="timing"),
                assistant_meta(question_topic="shot_result"),
            ],
            latest_analysis=None,
        )

        self.assertFalse(policy.question_allowed)
        self.assertEqual(policy.allowed_invite_modes, ())

    def test_positive_requires_analysis_and_three_turn_cooldown(self) -> None:
        without_analysis = build_conversation_policy(
            message="어때?",
            history=[],
            latest_analysis=None,
        )
        during_cooldown = build_conversation_policy(
            message="어때?",
            history=[assistant_meta(positive_topic="head_release")],
            latest_analysis={"conclusion": "검증된 분석"},
        )

        self.assertFalse(without_analysis.positive_allowed)
        self.assertFalse(during_cooldown.positive_allowed)

    def test_explicit_strength_request_overrides_cooldown_but_blocks_repeated_topic(self) -> None:
        policy = build_conversation_policy(
            message="내 스윙 장점도 말해줘",
            history=[assistant_meta(positive_topic="head_release")],
            latest_analysis={"conclusion": "검증된 분석"},
        )
        reply = ConversationReply(
            message="핵심 판정입니다.",
            positive_feedback="헤드 릴리스는 유지해야 합니다.",
            positive_topic="head_release",
        )

        enforced, metadata = enforce_conversation_policy(reply, policy, make_content(preserve=True))

        self.assertTrue(policy.positive_allowed)
        self.assertIsNone(enforced.positive_feedback)
        self.assertIsNone(metadata["positive_topic"])

    def test_response_length_mode_adapts_to_user_request(self) -> None:
        short = build_conversation_policy(
            message="왜 땡기지?",
            history=[],
            latest_analysis=None,
        )
        deep = build_conversation_policy(
            message="전체적으로 왜 그런지 자세히 설명해줘",
            history=[],
            latest_analysis=None,
        )

        self.assertEqual(short.response_mode, "short")
        self.assertEqual(deep.response_mode, "deep")

    def test_good_bad_contrast_prefers_a_question_and_has_a_fallback(self) -> None:
        policy = build_conversation_policy(
            message="잘 맞는 날에는 땡겨치는 느낌이 덜 그래",
            history=[],
            latest_analysis=None,
        )
        reply = ConversationReply(message="먼저 잘된 샷과 안 된 샷의 차이를 구분해야 해.")

        enforced, metadata = enforce_conversation_policy(reply, policy, make_content())

        self.assertTrue(policy.question_preferred)
        self.assertEqual(policy.preferred_invite_mode, "compare_good_bad")
        self.assertEqual(
            enforced.follow_up_question,
            "잘 맞은 샷과 안 맞은 샷에서는 어떤 느낌이 가장 달랐어?",
        )
        self.assertEqual(metadata["invite_mode"], "compare_good_bad")

    def test_default_context_is_irrelevant_to_general_goal_or_pro_reference(self) -> None:
        general_goal = build_conversation_policy(
            message="골프 잘 치고 싶엉",
            history=[],
            latest_analysis=None,
        )
        pro_reference = build_conversation_policy(
            message="나 매킬로이처럼 치고 싶은데",
            history=[],
            latest_analysis=None,
        )
        technical = build_conversation_policy(
            message="다운스윙 영상에서 손 위치가 왜 저래",
            history=[],
            latest_analysis=None,
        )

        self.assertFalse(general_goal.context_relevant)
        self.assertFalse(pro_reference.context_relevant)
        self.assertTrue(technical.context_relevant)
        self.assertEqual(general_goal.tone, "casual")
        self.assertTrue(general_goal.question_preferred)
        self.assertEqual(general_goal.preferred_invite_mode, "recall_specific_shot")

    def test_polite_user_message_selects_polite_tone(self) -> None:
        policy = build_conversation_policy(
            message="다운스윙을 자세히 설명해 주세요",
            history=[],
            latest_analysis=None,
        )

        self.assertEqual(policy.tone, "polite")


if __name__ == "__main__":
    unittest.main()
