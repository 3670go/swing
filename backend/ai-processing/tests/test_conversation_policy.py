import unittest

from app.conversation_policy import build_conversation_policy


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

    def test_explicit_strength_request_overrides_positive_cooldown(self) -> None:
        policy = build_conversation_policy(
            message="내 스윙 장점도 말해줘",
            history=[assistant_meta(positive_topic="head_release")],
            latest_analysis={"conclusion": "검증된 분석"},
        )
        self.assertTrue(policy.positive_allowed)
        self.assertIn("head_release", policy.blocked_positive_topics)

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

    def test_good_bad_contrast_prefers_compare_invite_mode(self) -> None:
        policy = build_conversation_policy(
            message="잘 맞는 날에는 땡겨치는 느낌이 덜 그래",
            history=[],
            latest_analysis=None,
        )
        self.assertTrue(policy.question_preferred)
        self.assertEqual(policy.preferred_invite_mode, "compare_good_bad")

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
