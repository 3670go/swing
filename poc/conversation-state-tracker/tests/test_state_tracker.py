"""상태 추적기 회귀 테스트.

실행: python -m unittest discover -s tests -t .

2026-08-28 검토에서 재현된 P0~P3 8건은 아래 RegressionP* 클래스로 고정한다.
"""

from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from baseline import (  # noqa: E402
    BASELINE_MIN_HISTORICAL_MESSAGES,
    BASELINE_MIN_TOTAL_USER_MESSAGES,
    BASELINE_RECENT_EXCLUSION,
    build_style_baseline,
)
from schemas import (  # noqa: E402
    Confidence,
    ConversationInput,
    ConversationState,
    DanglingReferenceError,
    DuplicateIdError,
    EngagementLevel,
    EngagementTrend,
    EvidenceReference,
    EvidenceSourceType,
    ExplicitIntent,
    InferredNeed,
    Message,
    NeedType,
    OpenLoopState,
    PriorStateConflictError,
    ProgressLevel,
    RecognitionIntensity,
    ResponseStrategy,
    validate_input_integrity,
)
from state_tracker import track  # noqa: E402

FIXTURES = ROOT / "fixtures"
NOW = datetime.fromisoformat("2026-08-28T12:00:00+09:00")

IRON_TOPIC = {
    "topic_id": "t2",
    "user_problem": "아이언에서 뒤땅이 난다",
    "root_problem": "체중이 오른발에 남는다",
}


def raw(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def load(name: str) -> ConversationInput:
    return ConversationInput.model_validate(raw(name))


def run(name: str) -> ConversationState:
    return track(load(name), now=NOW)


def run_raw(payload: dict) -> ConversationState:
    return track(ConversationInput.model_validate(payload), now=NOW)


def collect_refs(state: ConversationState) -> list[EvidenceReference]:
    refs = list(state.engagement_state.evidence) + list(state.progress.evidence)
    for need in state.inferred_needs:
        refs.extend(need.evidence)
    refs.extend(fact.source for fact in state.confirmed_user_facts)
    return refs


def semantic_verdict(state: ConversationState) -> dict[str, object]:
    """의미상 판정만 뽑는다. 메시지 ID, 시각, 원문은 비교 대상이 아니다."""
    return {
        "explicit_intent": state.explicit_intent.value,
        "engagement_level": state.engagement_state.level.value,
        "engagement_trend": state.engagement_state.trend.value,
        "engagement_confidence": state.engagement_state.confidence.value,
        "needs": sorted(
            (need.need_type.value, need.confidence.value) for need in state.inferred_needs
        ),
        "progress_level": state.progress.level.value,
        "swing_improvement_confirmed": state.progress.swing_improvement_confirmed,
        "recognition_intensity_cap": state.progress.recognition_intensity_cap.value,
        "primary_strategy": state.next_response_strategy.value,
        "secondary_strategy": (
            state.secondary_strategy.value if state.secondary_strategy else None
        ),
    }


# ==========================================================================
# 2026-08-28 검토 재현 8건 회귀 고정
# ==========================================================================


class RegressionP0TopicScopedContext(unittest.TestCase):
    """P0 — 활성 주제와 무관하게 마지막 12개를 선택하던 문제."""

    def test_only_active_topic_messages_are_selected(self) -> None:
        payload = raw("11_mixed_topics.json")
        topics = {m["message_id"]: m["topic_id"] for m in payload["messages"]}
        current = [m for m in payload["messages"] if m["role"] == "user"][-1]["message_id"]
        state = run_raw(payload)
        self.assertIn(current, state.selected_context_message_ids)
        for message_id in state.selected_context_message_ids:
            if message_id == current:
                continue
            self.assertEqual(topics[message_id], "t1", f"{message_id} 은 다른 주제 메시지다")

    def test_switching_topic_changes_selected_context(self) -> None:
        payload = raw("11_mixed_topics.json")
        topics = {m["message_id"]: m["topic_id"] for m in payload["messages"]}
        current = [m for m in payload["messages"] if m["role"] == "user"][-1]["message_id"]
        driver = run_raw(payload)

        switched = deepcopy(payload)
        switched["active_coaching_topic"] = IRON_TOPIC
        iron = run_raw(switched)

        self.assertNotEqual(driver.selected_context_message_ids, iron.selected_context_message_ids)
        for message_id in iron.selected_context_message_ids:
            if message_id == current:
                continue
            self.assertEqual(topics[message_id], "t2")

    def test_context_is_capped(self) -> None:
        for path in sorted(FIXTURES.glob("*.json")):
            with self.subTest(fixture=path.name):
                state = run(path.name)
                self.assertLessEqual(len(state.selected_context_message_ids), 12)


class RegressionP0OpenLoop(unittest.TestCase):
    """P0 — 무관한 이벤트 하나로 모든 PENDING Open Loop 가 종료되던 문제."""

    def test_unlinked_and_other_topic_events_do_not_fulfill(self) -> None:
        state = run("12_open_loop_unrelated_event.json")
        self.assertEqual([loop.open_loop_id for loop in state.unresolved_open_loops], ["ol1"])
        by_id = {loop.open_loop_id: loop for loop in state.open_loops}
        self.assertIs(by_id["ol1"].state, OpenLoopState.PENDING)
        self.assertIs(by_id["ol2"].state, OpenLoopState.PENDING)

    def test_linked_event_fulfills_only_that_loop(self) -> None:
        state = run("06_practice_result_improved.json")
        by_id = {loop.open_loop_id: loop for loop in state.open_loops}
        self.assertIs(by_id["ol1"].state, OpenLoopState.FULFILLED)
        self.assertEqual(state.unresolved_open_loops, [])

    def test_input_open_loops_are_not_mutated(self) -> None:
        payload = load("06_practice_result_improved.json")
        before = [loop.model_dump(mode="json") for loop in payload.open_loops]
        track(payload, now=NOW)
        after = [loop.model_dump(mode="json") for loop in payload.open_loops]
        self.assertEqual(before, after)

    def test_only_newest_pending_loop_in_topic_is_targeted(self) -> None:
        payload = raw("06_practice_result_improved.json")
        payload["open_loops"].append(
            {
                "open_loop_id": "ol0",
                "topic_id": "t1",
                "next_verification": "더 오래된 검증 계획이다.",
                "state": "PENDING",
                "created_at": "2026-08-20T09:00:00+09:00",
            }
        )
        state = run_raw(payload)
        by_id = {loop.open_loop_id: loop for loop in state.open_loops}
        self.assertIs(by_id["ol1"].state, OpenLoopState.FULFILLED)
        self.assertIs(by_id["ol0"].state, OpenLoopState.PENDING)


class RegressionP1VideoConfidence(unittest.TestCase):
    """P1 — LOW 신뢰도 영상과 비교 대상 없는 영상이 개선 확정으로 승격되던 문제."""

    def test_low_confidence_video_does_not_promote(self) -> None:
        state = run("13_low_confidence_video.json")
        self.assertIsNot(state.progress.level, ProgressLevel.VIDEO_VERIFIED_PROGRESS)
        self.assertFalse(state.progress.swing_improvement_confirmed)
        self.assertIsNot(state.progress.confidence, Confidence.HIGH)

    def test_low_confidence_video_does_not_create_result_repeated(self) -> None:
        state = run("13_low_confidence_video.json")
        self.assertIsNot(state.progress.level, ProgressLevel.RESULT_REPEATED)

    def test_video_without_comparison_target_does_not_promote(self) -> None:
        state = run("14_video_without_comparison_target.json")
        self.assertIsNot(state.progress.level, ProgressLevel.VIDEO_VERIFIED_PROGRESS)
        self.assertFalse(state.progress.swing_improvement_confirmed)

    def test_dangling_comparison_target_is_rejected(self) -> None:
        payload = raw("06b_video_verified_progress.json")
        payload["video_evidence"] = [payload["video_evidence"][1]]  # a0 제거
        with self.assertRaises(DanglingReferenceError):
            run_raw(payload)

    def test_self_comparison_is_rejected(self) -> None:
        payload = raw("06b_video_verified_progress.json")
        payload["video_evidence"][1]["compared_to_analysis_id"] = payload["video_evidence"][1][
            "analysis_id"
        ]
        with self.assertRaises(DanglingReferenceError):
            run_raw(payload)

    def test_result_confidence_never_exceeds_video_confidence(self) -> None:
        payload = raw("06b_video_verified_progress.json")
        payload["video_evidence"][1]["confidence"] = "MEDIUM"
        state = run_raw(payload)
        self.assertIs(state.progress.level, ProgressLevel.VIDEO_VERIFIED_PROGRESS)
        self.assertIs(state.progress.confidence, Confidence.MEDIUM)


class RegressionP1BaselineBoundary(unittest.TestCase):
    """P1 — 상수는 6인데 실제로는 9개부터 생성되던 불일치."""

    @staticmethod
    def _messages(count: int) -> list[Message]:
        return [
            Message(
                message_id=f"m{i}",
                role="user",
                text="드라이버 전환 구간에서 팔이 내려올 공간이 부족하다고 느낍니다",
                created_at=NOW,
            )
            for i in range(count)
        ]

    def test_constants_agree_with_each_other(self) -> None:
        self.assertEqual(
            BASELINE_MIN_TOTAL_USER_MESSAGES,
            BASELINE_MIN_HISTORICAL_MESSAGES + BASELINE_RECENT_EXCLUSION,
        )

    def test_boundary_six_seven_eight_nine(self) -> None:
        for count, expected in ((6, False), (7, False), (8, False), (9, True), (10, True)):
            with self.subTest(user_messages=count):
                created = build_style_baseline(self._messages(count), []) is not None
                self.assertEqual(created, expected)

    def test_pool_excludes_recent_messages(self) -> None:
        baseline = build_style_baseline(self._messages(9), [])
        self.assertIsNotNone(baseline)
        self.assertEqual(baseline.sample_size, 9 - BASELINE_RECENT_EXCLUSION)


class RegressionP1InputIntegrity(unittest.TestCase):
    """P1 — 중복 ID 와 존재하지 않는 관계 ID 가 검사되지 않던 문제."""

    def test_duplicate_message_id_is_rejected(self) -> None:
        payload = raw("06_practice_result_improved.json")
        clone = deepcopy(payload["messages"][0])
        payload["messages"].append(clone)
        with self.assertRaises(DuplicateIdError):
            run_raw(payload)

    def test_duplicate_behavior_event_id_is_rejected(self) -> None:
        payload = raw("06_practice_result_improved.json")
        payload["behavior_events"].append(deepcopy(payload["behavior_events"][0]))
        with self.assertRaises(DuplicateIdError):
            run_raw(payload)

    def test_same_id_across_different_source_types_is_allowed(self) -> None:
        payload = raw("06_practice_result_improved.json")
        payload["behavior_events"][0]["event_id"] = "m1"
        payload["behavior_events"][0]["open_loop_id"] = None
        validate_input_integrity(ConversationInput.model_validate(payload))

    def test_dangling_related_message_id_is_rejected(self) -> None:
        payload = raw("06_practice_result_improved.json")
        payload["behavior_events"][0]["related_message_id"] = "does-not-exist"
        with self.assertRaises(DanglingReferenceError):
            run_raw(payload)

    def test_dangling_open_loop_id_is_rejected(self) -> None:
        payload = raw("06_practice_result_improved.json")
        payload["behavior_events"][0]["open_loop_id"] = "does-not-exist"
        with self.assertRaises(DanglingReferenceError):
            run_raw(payload)

    def test_feedback_must_target_an_assistant_message(self) -> None:
        payload = raw("07_feedback_actual_effect.json")
        payload["feedback_events"][0]["target_message_id"] = "m2"  # 사용자 메시지
        with self.assertRaises(DanglingReferenceError):
            run_raw(payload)

    def test_prior_state_topic_conflict_is_rejected(self) -> None:
        payload = raw("08_user_correction_of_inference.json")
        payload["active_coaching_topic"] = IRON_TOPIC
        with self.assertRaises(PriorStateConflictError):
            run_raw(payload)


class RegressionP1DuplicateResultCounting(unittest.TestCase):
    """P1 — 같은 결과의 행동+피드백이 두 번으로 세어지던 문제."""

    def test_same_result_counted_once(self) -> None:
        state = run("15_duplicate_result_reports.json")
        self.assertIs(state.progress.level, ProgressLevel.USER_REPORTED_PROGRESS)
        self.assertIs(
            state.progress.recognition_intensity_cap, RecognitionIntensity.ACKNOWLEDGEMENT
        )

    def test_two_distinct_results_promote(self) -> None:
        state = run("16_two_distinct_results.json")
        self.assertIs(state.progress.level, ProgressLevel.RESULT_REPEATED)
        self.assertIs(
            state.progress.recognition_intensity_cap, RecognitionIntensity.SPECIFIC_RECOGNITION
        )
        self.assertFalse(state.progress.swing_improvement_confirmed)


class RegressionP2InferenceHistory(unittest.TestCase):
    """P2 — 변경 이력이 사라진 니즈만, 그것도 최신 메시지 trigger 로만 남던 문제."""

    def test_removed_and_added_are_both_recorded(self) -> None:
        state = run("08_user_correction_of_inference.json")
        removed = [
            r
            for r in state.inference_history
            if r.previous_inference and r.previous_inference.need_type is NeedType.NEEDS_CERTAINTY
        ]
        added = [
            r
            for r in state.inference_history
            if r.new_inference and r.new_inference.need_type is NeedType.NEEDS_SIMPLER_EXPLANATION
        ]
        self.assertTrue(removed, "철회된 추정이 기록되지 않았다")
        self.assertTrue(added, "새로 추가된 추정이 기록되지 않았다")
        self.assertIsNone(removed[0].new_inference)
        self.assertIsNone(added[0].previous_inference)
        self.assertIsNotNone(removed[0].previous_inference.confidence)
        self.assertTrue(removed[0].previous_inference.evidence)

    def test_addition_only_is_recorded_with_non_message_trigger(self) -> None:
        current = raw("07_feedback_actual_effect.json")
        prior_payload = deepcopy(current)
        prior_payload["feedback_events"] = []
        prior = run_raw(prior_payload)
        self.assertEqual(prior.inferred_needs, [])

        current["prior_state"] = prior.model_dump(mode="json")
        state = run_raw(current)
        added = [r for r in state.inference_history if r.new_inference is not None]
        self.assertEqual(len(added), 1)
        self.assertIs(added[0].new_inference.need_type, NeedType.NEEDS_PROGRESS_RECOGNITION)
        self.assertIsNone(added[0].previous_inference)
        self.assertTrue(
            any(
                ref.source_type is EvidenceSourceType.FEEDBACK_EVENT
                for ref in added[0].trigger_evidence
            ),
            "행동·피드백 근거로 바뀌었는데 trigger 가 메시지로만 기록됐다",
        )

    def test_one_need_becomes_many(self) -> None:
        base = raw("08_user_correction_of_inference.json")
        prior = ConversationState.model_validate(base["prior_state"])
        self.assertEqual([n.need_type for n in prior.inferred_needs], [NeedType.NEEDS_CERTAINTY])

        payload = deepcopy(base)
        payload["messages"].append(
            {
                "message_id": "m7",
                "role": "user",
                "text": "그러면 뭐부터 연습해야 돼요?",
                "created_at": "2026-08-27T15:00:00+09:00",
                "topic_id": "t1",
            }
        )
        state = run_raw(payload)
        current_types = {need.need_type for need in state.inferred_needs}
        self.assertGreaterEqual(len(current_types), 2)
        added = {r.new_inference.need_type for r in state.inference_history if r.new_inference}
        self.assertEqual(added, current_types)

    def test_many_needs_become_one(self) -> None:
        base = raw("08_user_correction_of_inference.json")
        prior = ConversationState.model_validate(base["prior_state"])
        extra = InferredNeed(
            need_type=NeedType.NEEDS_ACTIONABLE_STEP,
            confidence=Confidence.MEDIUM,
            evidence=[EvidenceReference(source_type=EvidenceSourceType.MESSAGE, source_id="m2")],
            reason="테스트용 이전 추정",
            last_updated_at=NOW,
        )
        prior_two = prior.model_copy(update={"inferred_needs": [*prior.inferred_needs, extra]})
        payload = deepcopy(base)
        payload["prior_state"] = prior_two.model_dump(mode="json")
        state = run_raw(payload)
        self.assertEqual(
            [need.need_type for need in state.inferred_needs],
            [NeedType.NEEDS_SIMPLER_EXPLANATION],
        )
        removed = {
            r.previous_inference.need_type
            for r in state.inference_history
            if r.previous_inference and r.new_inference is None
        }
        self.assertEqual(removed, {NeedType.NEEDS_CERTAINTY, NeedType.NEEDS_ACTIONABLE_STEP})

    def test_history_is_appended_not_replaced(self) -> None:
        state = run("08_user_correction_of_inference.json")
        prior = ConversationState.model_validate(
            raw("08_user_correction_of_inference.json")["prior_state"]
        )
        self.assertGreaterEqual(len(state.inference_history), len(prior.inference_history))


class RegressionP2EngagementEventScope(unittest.TestCase):
    """P2 — 오래된 이벤트와 다른 주제 이벤트가 현재 참여도를 올리던 문제."""

    def test_stale_event_does_not_raise_engagement(self) -> None:
        state = run("17_stale_behavior_event.json")
        self.assertIsNot(state.engagement_state.level, EngagementLevel.HIGH)

    def test_other_topic_event_does_not_raise_engagement(self) -> None:
        state = run("18_other_topic_behavior_event.json")
        self.assertIsNot(state.engagement_state.level, EngagementLevel.HIGH)
        for ref in state.engagement_state.evidence:
            self.assertIsNot(ref.source_type, EvidenceSourceType.BEHAVIOR_EVENT)

    def test_current_turn_event_is_included_as_evidence(self) -> None:
        payload = raw("17_stale_behavior_event.json")
        last_user = [m for m in payload["messages"] if m["role"] == "user"][-1]
        payload["behavior_events"] = [
            {
                "event_id": "b_now",
                "event_type": "VIDEO_UPLOADED",
                "related_message_id": last_user["message_id"],
                "created_at": last_user["created_at"],
                "topic_id": "t1",
                "open_loop_id": None,
            }
        ]
        state = run_raw(payload)
        self.assertIs(state.engagement_state.level, EngagementLevel.HIGH)
        self.assertTrue(
            any(
                ref.source_type is EvidenceSourceType.BEHAVIOR_EVENT
                for ref in state.engagement_state.evidence
            )
        )


# ==========================================================================
# 기존 원칙 회귀
# ==========================================================================


class ShortReplyOverInterpretation(unittest.TestCase):
    """단일 짧은 응답을 과도하게 해석하지 않는지 확인하는 내부 회귀 테스트.

    POC 목표나 사용자 화면의 주제가 아니다. 여기 한 곳에서만 검증한다.
    """

    def test_single_short_reply_is_not_over_interpreted(self) -> None:
        first = run("01_acknowledgement_without_baseline.json")
        second = run("02_acknowledgement_variant_neb.json")

        for state in (first, second):
            self.assertIsNone(state.style_baseline)
            self.assertIs(state.engagement_state.level, EngagementLevel.UNKNOWN)
            self.assertIs(state.engagement_state.trend, EngagementTrend.UNKNOWN)
            self.assertIs(state.engagement_state.confidence, Confidence.LOW)
            self.assertEqual(state.inferred_needs, [])
            self.assertIs(state.explicit_intent, ExplicitIntent.UNKNOWN)
            self.assertIs(state.next_response_strategy, ResponseStrategy.DO_NOT_INFER)

        self.assertEqual(semantic_verdict(first), semantic_verdict(second))
        self.assertNotEqual(
            first.model_dump(mode="json"),
            second.model_dump(mode="json"),
            "원문과 ID 가 다르므로 전체 JSON 은 달라야 정상이다",
        )


class ShortRepliesAgainstBaseline(unittest.TestCase):
    def test_only_possible_decline_is_inferred(self) -> None:
        state = run("03_short_replies_against_baseline.json")
        self.assertIsNotNone(state.style_baseline)
        self.assertIs(state.engagement_state.trend, EngagementTrend.DECREASING)
        self.assertIn(state.engagement_state.confidence, (Confidence.LOW, Confidence.MEDIUM))
        self.assertGreaterEqual(len(state.engagement_state.evidence), 1)

    def test_no_dissatisfaction_or_churn_conclusion(self) -> None:
        state = run("03_short_replies_against_baseline.json")
        serialized = json.dumps(state.model_dump(mode="json"), ensure_ascii=False)
        for banned in ("불만", "이탈", "DISSATISFIED", "CHURN"):
            self.assertNotIn(banned, serialized)


class ExplicitIntentAndFacts(unittest.TestCase):
    def test_cause_question_without_video(self) -> None:
        state = run("04_explicit_cause_question.json")
        self.assertIs(state.explicit_intent, ExplicitIntent.CAUSE_EXPLANATION)
        video_facts = [
            f for f in state.confirmed_user_facts if f.evidence_level == "VIDEO_OBSERVED"
        ]
        self.assertEqual(video_facts, [], "영상이 없으면 스윙 원인을 확정하지 않는다")

    def test_repeated_confirmation_is_low_confidence(self) -> None:
        state = run("05_repeated_direction_confirmation.json")
        needs = {need.need_type: need for need in state.inferred_needs}
        self.assertIn(NeedType.NEEDS_CERTAINTY, needs)
        self.assertIs(needs[NeedType.NEEDS_CERTAINTY].confidence, Confidence.LOW)


class UserReportedVersusVideoVerified(unittest.TestCase):
    def test_user_report_is_not_verified_swing_improvement(self) -> None:
        state = run("06_practice_result_improved.json")
        self.assertIs(state.progress.level, ProgressLevel.USER_REPORTED_PROGRESS)
        self.assertFalse(state.progress.swing_improvement_confirmed)
        self.assertIs(
            state.progress.recognition_intensity_cap, RecognitionIntensity.ACKNOWLEDGEMENT
        )
        self.assertIs(state.next_response_strategy, ResponseStrategy.RECOGNIZE_MEANINGFUL_PROGRESS)
        self.assertIs(state.secondary_strategy, ResponseStrategy.OPEN_NEXT_PRACTICE_LOOP)

    def test_video_comparison_raises_evidence_level(self) -> None:
        state = run("06b_video_verified_progress.json")
        self.assertIs(state.progress.level, ProgressLevel.VIDEO_VERIFIED_PROGRESS)
        self.assertTrue(state.progress.swing_improvement_confirmed)
        self.assertIs(
            state.progress.recognition_intensity_cap, RecognitionIntensity.PROGRESS_DECLARATION
        )

    def test_ordering_between_the_two(self) -> None:
        reported = run("06_practice_result_improved.json")
        verified = run("06b_video_verified_progress.json")
        order = list(ProgressLevel)
        self.assertLess(order.index(reported.progress.level), order.index(verified.progress.level))


class FeedbackVersusOutcome(unittest.TestCase):
    def test_like_alone_is_not_progress(self) -> None:
        state = run("07b_feedback_helpful_only.json")
        self.assertIs(state.progress.level, ProgressLevel.NONE)
        self.assertIsNot(
            state.next_response_strategy, ResponseStrategy.RECOGNIZE_MEANINGFUL_PROGRESS
        )

    def test_actual_effect_is_stronger_evidence(self) -> None:
        state = run("07_feedback_actual_effect.json")
        self.assertIs(state.progress.level, ProgressLevel.USER_REPORTED_PROGRESS)
        self.assertFalse(state.progress.swing_improvement_confirmed)
        self.assertTrue(
            any(
                ref.source_type is EvidenceSourceType.FEEDBACK_EVENT
                for ref in state.progress.evidence
            )
        )


class ProfanityWithinBaseline(unittest.TestCase):
    def test_profanity_does_not_become_negative_emotion(self) -> None:
        state = run("09_profanity_within_baseline.json")
        self.assertIsNotNone(state.style_baseline)
        self.assertGreaterEqual(state.style_baseline.profanity_ratio, 0.3)
        self.assertIs(state.engagement_state.trend, EngagementTrend.STABLE)
        self.assertIsNot(state.engagement_state.level, EngagementLevel.LOW)


class VideoVersusFeel(unittest.TestCase):
    def test_video_observation_drives_reframing(self) -> None:
        state = run("10_video_evidence_conflicts_with_feel.json")
        video_facts = [
            f for f in state.confirmed_user_facts if f.evidence_level == "VIDEO_OBSERVED"
        ]
        self.assertTrue(video_facts)
        self.assertIn(
            NeedType.NEEDS_PROBLEM_REFRAMING, {need.need_type for need in state.inferred_needs}
        )

    def test_feel_does_not_become_a_video_observation(self) -> None:
        payload = load("10_video_evidence_conflicts_with_feel.json")
        state = track(payload, now=NOW)
        user_texts = {m.text for m in payload.messages if m.role == "user"}
        for fact in state.confirmed_user_facts:
            if fact.evidence_level == "VIDEO_OBSERVED":
                self.assertNotIn(fact.statement, user_texts)


class VideoEvidenceImmutability(unittest.TestCase):
    """frozen 설정이 아니라 실제 동작으로 검증한다."""

    NAMES = (
        "06b_video_verified_progress.json",
        "10_video_evidence_conflicts_with_feel.json",
        "13_low_confidence_video.json",
        "14_video_without_comparison_target.json",
    )

    def test_input_video_evidence_is_unchanged(self) -> None:
        for name in self.NAMES:
            with self.subTest(name=name):
                payload = load(name)
                before = deepcopy([v.model_dump(mode="json") for v in payload.video_evidence])
                track(payload, now=NOW)
                after = [v.model_dump(mode="json") for v in payload.video_evidence]
                self.assertEqual(before, after)

    def test_only_existing_analysis_ids_are_referenced(self) -> None:
        for name in self.NAMES:
            with self.subTest(name=name):
                payload = load(name)
                known = {v.analysis_id for v in payload.video_evidence}
                refs = [
                    ref
                    for ref in collect_refs(track(payload, now=NOW))
                    if ref.source_type is EvidenceSourceType.VIDEO_ANALYSIS
                ]
                self.assertTrue(refs)
                for ref in refs:
                    self.assertIn(ref.source_id, known)

    def test_no_new_observation_text_is_produced(self) -> None:
        for name in self.NAMES:
            with self.subTest(name=name):
                payload = load(name)
                allowed = {
                    observation
                    for evidence in payload.video_evidence
                    for observation in evidence.observations
                }
                for fact in track(payload, now=NOW).confirmed_user_facts:
                    if fact.evidence_level == "VIDEO_OBSERVED":
                        self.assertIn(
                            fact.statement,
                            allowed,
                            "영상 관찰은 글자 그대로만 인용한다. 요약·재작성·신규 생성 금지",
                        )


class EvidenceContract(unittest.TestCase):
    def test_every_inference_carries_evidence(self) -> None:
        for path in sorted(FIXTURES.glob("*.json")):
            with self.subTest(fixture=path.name):
                state = run(path.name)
                self.assertGreaterEqual(len(state.engagement_state.evidence), 1)
                self.assertGreaterEqual(len(state.progress.evidence), 1)
                for need in state.inferred_needs:
                    self.assertGreaterEqual(len(need.evidence), 1)
                for revision in state.inference_history:
                    self.assertGreaterEqual(len(revision.trigger_evidence), 1)

    def test_all_evidence_source_ids_exist_in_input(self) -> None:
        for path in sorted(FIXTURES.glob("*.json")):
            with self.subTest(fixture=path.name):
                payload = load(path.name)
                known = {
                    EvidenceSourceType.MESSAGE: {m.message_id for m in payload.messages},
                    EvidenceSourceType.BEHAVIOR_EVENT: {
                        e.event_id for e in payload.behavior_events
                    },
                    EvidenceSourceType.FEEDBACK_EVENT: {
                        e.feedback_id for e in payload.feedback_events
                    },
                    EvidenceSourceType.VIDEO_ANALYSIS: {
                        v.analysis_id for v in payload.video_evidence
                    },
                }
                for ref in collect_refs(track(payload, now=NOW)):
                    self.assertIn(ref.source_id, known[ref.source_type])

    def test_all_four_source_types_are_usable(self) -> None:
        seen: set[EvidenceSourceType] = set()
        for path in sorted(FIXTURES.glob("*.json")):
            seen.update(ref.source_type for ref in collect_refs(run(path.name)))
        self.assertEqual(seen, set(EvidenceSourceType))


class RawAndDerivedSeparation(unittest.TestCase):
    def test_messages_are_not_mutated(self) -> None:
        for path in sorted(FIXTURES.glob("*.json")):
            with self.subTest(fixture=path.name):
                payload = load(path.name)
                before = [m.model_dump(mode="json") for m in payload.messages]
                track(payload, now=NOW)
                after = [m.model_dump(mode="json") for m in payload.messages]
                self.assertEqual(before, after)


class StrategyLimits(unittest.TestCase):
    def test_at_most_one_primary_and_one_secondary(self) -> None:
        for path in sorted(FIXTURES.glob("*.json")):
            with self.subTest(fixture=path.name):
                state = run(path.name)
                if state.secondary_strategy is not None:
                    self.assertNotEqual(state.secondary_strategy, state.next_response_strategy)


if __name__ == "__main__":
    unittest.main()
