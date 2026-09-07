"""ConversationState 조립.

원본 메시지는 읽기만 한다. 파생 상태만 새로 만든다.
근거 없는 추정은 만들지 않고, 입력에 없는 ID 를 참조하지 않는다.
활성 코칭 주제가 있으면 그 주제 밖의 메시지·이벤트는 사용하지 않는다.
"""

from __future__ import annotations

from datetime import datetime

from baseline import (
    build_style_baseline,
    is_bare_acknowledgement,
    is_habitual_profanity,
    recent_short_reply_streak,
)
from schemas import (
    BehaviorEventType,
    Confidence,
    ConfirmedFact,
    ConversationInput,
    ConversationState,
    DanglingReferenceError,
    EngagementLevel,
    EngagementState,
    EngagementTrend,
    EvidenceReference,
    EvidenceSourceType,
    InferenceRevision,
    InferenceWithoutEvidenceError,
    InferredNeed,
    NeedType,
    OpenLoopRef,
    OpenLoopState,
    ProgressAssessment,
    ProgressLevel,
    RecognitionIntensity,
    StyleBaseline,
    VideoEvidenceMutationError,
    validate_input_integrity,
)
from signals import (
    Scope,
    actionable_evidence,
    behavior_ref,
    build_scope,
    classify_progress_level,
    current_turn_behavior_events,
    detect_explicit_intent,
    difficulty_evidence,
    is_correction_of_inference,
    message_ref,
    progress_recognition_evidence,
    reframing_evidence,
    repeated_confirmation_evidence,
    user_reported_progress_messages,
)
from strategy import select_strategy

MAX_CONTEXT_MESSAGES = 12
"""계약 §9.4 의 '현재 topic 최근 메시지 최대 12개'를 따른 상한."""

INTENSITY_CAP_BY_LEVEL = {
    ProgressLevel.NONE: RecognitionIntensity.NONE,
    ProgressLevel.USER_REPORTED_PROGRESS: RecognitionIntensity.ACKNOWLEDGEMENT,
    ProgressLevel.RESULT_REPEATED: RecognitionIntensity.SPECIFIC_RECOGNITION,
    ProgressLevel.VIDEO_VERIFIED_PROGRESS: RecognitionIntensity.PROGRESS_DECLARATION,
}

REFRAME_KEYWORDS = ("팔", "전환", "몸통", "손", "체중", "머리", "어깨", "골반", "손목")


def _known_ids(payload: ConversationInput) -> dict[EvidenceSourceType, set[str]]:
    return {
        EvidenceSourceType.MESSAGE: {m.message_id for m in payload.messages},
        EvidenceSourceType.BEHAVIOR_EVENT: {e.event_id for e in payload.behavior_events},
        EvidenceSourceType.FEEDBACK_EVENT: {e.feedback_id for e in payload.feedback_events},
        EvidenceSourceType.VIDEO_ANALYSIS: {v.analysis_id for v in payload.video_evidence},
    }


def _validate_evidence(
    refs: list[EvidenceReference], known: dict[EvidenceSourceType, set[str]]
) -> list[EvidenceReference]:
    if not refs:
        raise InferenceWithoutEvidenceError("추정에는 최소 하나의 근거가 필요하다")
    deduped: list[EvidenceReference] = []
    seen: set[EvidenceReference] = set()
    for ref in refs:
        if ref.source_id not in known[ref.source_type]:
            raise DanglingReferenceError(
                f"입력에 없는 근거를 참조했다: {ref.source_type.value}:{ref.source_id}"
            )
        if ref not in seen:
            seen.add(ref)
            deduped.append(ref)
    return deduped


# --------------------------------------------------------------------------
# Engagement
# --------------------------------------------------------------------------


def _build_engagement(
    scope: Scope, baseline: StyleBaseline | None, now: datetime, known
) -> EngagementState:
    latest = scope.latest_user_message

    if baseline is None:
        return EngagementState(
            level=EngagementLevel.UNKNOWN,
            trend=EngagementTrend.UNKNOWN,
            confidence=Confidence.LOW,
            evidence=_validate_evidence([message_ref(latest)], known),
            reason=(
                "사용자 기준선이 없다. 단일 표현만으로 참여도를 판정하지 않는다"
                if is_bare_acknowledgement(latest.text)
                else "사용자 기준선을 만들 표본이 부족하다"
            ),
            last_updated_at=now,
        )

    streak = recent_short_reply_streak(scope.messages, baseline)
    if len(streak) >= 2:
        confidence = Confidence.MEDIUM if len(streak) >= 3 else Confidence.LOW
        level = EngagementLevel.LOW if len(streak) >= 3 else EngagementLevel.MEDIUM
        return EngagementState(
            level=level,
            trend=EngagementTrend.DECREASING,
            confidence=confidence,
            evidence=_validate_evidence([message_ref(m) for m in streak], known),
            reason=(
                f"평소 평균 {baseline.average_message_length}자 대비 짧은 반응이 "
                f"{len(streak)}회 연속됐다. 참여도 감소 가능성만 본다"
            ),
            last_updated_at=now,
        )

    active_events = [
        event
        for event in current_turn_behavior_events(scope)
        if event.event_type
        in (
            BehaviorEventType.VIDEO_UPLOADED,
            BehaviorEventType.PRACTICE_RESULT_REPORTED,
            BehaviorEventType.FOLLOW_UP_QUESTION,
        )
    ]
    if active_events:
        return EngagementState(
            level=EngagementLevel.HIGH,
            trend=EngagementTrend.STABLE,
            confidence=Confidence.MEDIUM,
            evidence=_validate_evidence(
                [behavior_ref(event) for event in active_events] + [message_ref(latest)], known
            ),
            reason="이번 turn 의 현재 주제 행동 이벤트가 있다",
            last_updated_at=now,
        )
    return EngagementState(
        level=EngagementLevel.MEDIUM,
        trend=EngagementTrend.STABLE,
        confidence=Confidence.MEDIUM,
        evidence=_validate_evidence([message_ref(latest)], known),
        reason="최근 반응이 기준선 범위 안에 있다",
        last_updated_at=now,
    )


# --------------------------------------------------------------------------
# Needs
# --------------------------------------------------------------------------


def _shares_keyword(user_words: str, observations: str) -> bool:
    user_tokens = {k for k in REFRAME_KEYWORDS if k in user_words}
    observation_tokens = {k for k in REFRAME_KEYWORDS if k in observations}
    if not user_tokens or not observation_tokens:
        return True
    return bool(user_tokens & observation_tokens)


def _build_needs(
    payload: ConversationInput, scope: Scope, baseline: StyleBaseline | None, now: datetime, known
) -> list[InferredNeed]:
    needs: list[InferredNeed] = []
    latest = scope.latest_user_message

    if baseline is None and is_bare_acknowledgement(latest.text) and not scope.behavior_events:
        return needs

    difficulty = difficulty_evidence(scope)
    if difficulty:
        needs.append(
            InferredNeed(
                need_type=NeedType.NEEDS_SIMPLER_EXPLANATION,
                confidence=Confidence.MEDIUM,
                evidence=_validate_evidence(difficulty, known),
                reason="사용자가 이해 난이도 또는 길이를 직접 문제로 말했다",
                last_updated_at=now,
            )
        )

    repeated = repeated_confirmation_evidence(scope)
    if repeated and not difficulty:
        needs.append(
            InferredNeed(
                need_type=NeedType.NEEDS_CERTAINTY,
                confidence=Confidence.LOW,
                evidence=_validate_evidence(repeated, known),
                reason="같은 방향을 반복 확인했다. 불안이나 불신으로 확정하지 않는다",
                last_updated_at=now,
            )
        )

    actionable = actionable_evidence(scope)
    if actionable:
        needs.append(
            InferredNeed(
                need_type=NeedType.NEEDS_ACTIONABLE_STEP,
                confidence=Confidence.MEDIUM,
                evidence=_validate_evidence(actionable, known),
                reason="사용자가 다음에 할 행동을 직접 물었다",
                last_updated_at=now,
            )
        )

    recognition = progress_recognition_evidence(scope)
    if recognition:
        needs.append(
            InferredNeed(
                need_type=NeedType.NEEDS_PROGRESS_RECOGNITION,
                confidence=Confidence.MEDIUM,
                evidence=_validate_evidence(recognition, known),
                reason="사용자가 실행 결과를 보고했다",
                last_updated_at=now,
            )
        )

    if scope.video_evidence and payload.active_coaching_topic is not None:
        user_words = " ".join(m.text for m in scope.messages if m.role == "user")
        observations = " ".join(o for v in scope.video_evidence for o in v.observations)
        if not _shares_keyword(user_words, observations):
            needs.append(
                InferredNeed(
                    need_type=NeedType.NEEDS_PROBLEM_REFRAMING,
                    confidence=Confidence.MEDIUM,
                    evidence=_validate_evidence(reframing_evidence(scope), known),
                    reason="사용자가 말한 원인과 영상 관찰의 초점이 다르다",
                    last_updated_at=now,
                )
            )

    if is_habitual_profanity(baseline):
        # 평소 표현이다. 부정 감정 니즈를 만들지 않는다.
        pass

    return needs


# --------------------------------------------------------------------------
# Progress and facts
# --------------------------------------------------------------------------


def _build_progress(scope: Scope, now: datetime, known) -> ProgressAssessment:
    level, refs, reason, confidence = classify_progress_level(scope)
    if level is ProgressLevel.NONE:
        return ProgressAssessment(
            level=level,
            swing_improvement_confirmed=False,
            recognition_intensity_cap=RecognitionIntensity.NONE,
            confidence=Confidence.LOW,
            evidence=_validate_evidence([message_ref(scope.latest_user_message)], known),
            reason=reason,
            last_updated_at=now,
        )
    return ProgressAssessment(
        level=level,
        swing_improvement_confirmed=level is ProgressLevel.VIDEO_VERIFIED_PROGRESS,
        recognition_intensity_cap=INTENSITY_CAP_BY_LEVEL[level],
        confidence=confidence,
        evidence=_validate_evidence(refs, known),
        reason=reason,
        last_updated_at=now,
    )


def _build_confirmed_facts(scope: Scope, known) -> list[ConfirmedFact]:
    """사용자 발화와 영상 관찰만. 요약하거나 새 문장을 만들지 않는다."""
    facts: list[ConfirmedFact] = []
    for message in user_reported_progress_messages(scope):
        facts.append(
            ConfirmedFact(
                statement=message.text,
                source=_validate_evidence([message_ref(message)], known)[0],
                evidence_level="USER_REPORTED",
            )
        )
    for evidence in scope.video_evidence:
        for observation in evidence.observations:
            facts.append(
                ConfirmedFact(
                    statement=observation,
                    source=EvidenceReference(
                        source_type=EvidenceSourceType.VIDEO_ANALYSIS,
                        source_id=evidence.analysis_id,
                    ),
                    evidence_level="VIDEO_OBSERVED",
                )
            )
    return facts


# --------------------------------------------------------------------------
# Open loops
# --------------------------------------------------------------------------


FULFILLING_EVENT_TYPES = (
    BehaviorEventType.PRACTICE_RESULT_REPORTED,
    BehaviorEventType.VIDEO_UPLOADED,
)


def _resolve_open_loops(
    payload: ConversationInput, scope: Scope
) -> tuple[list[OpenLoopRef], list[OpenLoopRef]]:
    """이벤트에 연결되고 현재 주제인 최신 PENDING Open Loop 하나만 FULFILLED 로 바꾼다.

    입력 객체는 변경하지 않는다. 새 OpenLoopRef 목록을 만들어 돌려준다.
    """
    topic_id = scope.topic_id
    pending_in_topic = [
        loop
        for loop in payload.open_loops
        if loop.state is OpenLoopState.PENDING and (topic_id is None or loop.topic_id == topic_id)
    ]
    target: OpenLoopRef | None = None
    if pending_in_topic:
        newest = max(pending_in_topic, key=lambda loop: loop.created_at)
        for event in scope.behavior_events:
            if event.event_type not in FULFILLING_EVENT_TYPES:
                continue
            if event.open_loop_id is None:
                continue
            if event.open_loop_id != newest.open_loop_id:
                continue
            target = newest
            break

    all_loops: list[OpenLoopRef] = []
    for loop in payload.open_loops:
        if target is not None and loop.open_loop_id == target.open_loop_id:
            all_loops.append(loop.model_copy(update={"state": OpenLoopState.FULFILLED}))
        else:
            all_loops.append(loop)

    unresolved = [
        loop
        for loop in all_loops
        if loop.state is OpenLoopState.PENDING and (topic_id is None or loop.topic_id == topic_id)
    ]
    return all_loops, unresolved


# --------------------------------------------------------------------------
# Context selection
# --------------------------------------------------------------------------


def _select_context_message_ids(
    payload: ConversationInput, scope: Scope, refs: list[EvidenceReference]
) -> list[str]:
    """현재 사용자 메시지 → 같은 topic 메시지 → 해당 topic 근거 메시지, 최대 12개."""
    latest = scope.latest_user_message
    selectable = {m.message_id for m in scope.messages}
    order = {m.message_id: i for i, m in enumerate(payload.messages)}

    selected: list[str] = [latest.message_id]
    for message in reversed(scope.messages):
        if len(selected) >= MAX_CONTEXT_MESSAGES:
            break
        if message.message_id not in selected:
            selected.append(message.message_id)
    for ref in refs:
        if len(selected) >= MAX_CONTEXT_MESSAGES:
            break
        if ref.source_type is not EvidenceSourceType.MESSAGE:
            continue
        if ref.source_id in selected or ref.source_id not in selectable:
            continue
        selected.append(ref.source_id)
    return sorted(selected, key=lambda mid: order[mid])


# --------------------------------------------------------------------------
# Inference history
# --------------------------------------------------------------------------


def _all_refs(state_needs: list[InferredNeed], *others: list[EvidenceReference]) -> set:
    refs: set = set()
    for need in state_needs:
        refs.update(need.evidence)
    for group in others:
        refs.update(group)
    return refs


def _build_history(
    payload: ConversationInput,
    scope: Scope,
    needs: list[InferredNeed],
    current_refs: list[EvidenceReference],
    now: datetime,
    known,
) -> list[InferenceRevision]:
    """이전 추정은 지우지 않고 변경 이력으로 남긴다.

    trigger 는 이번 입력에서 새로 등장한 근거다. 최신 사용자 메시지를 무조건 쓰지 않는다.
    """
    prior = payload.prior_state
    history: list[InferenceRevision] = list(prior.inference_history) if prior else []
    if prior is None:
        return history

    previous_by_type = {need.need_type: need for need in prior.inferred_needs}
    current_by_type = {need.need_type: need for need in needs}

    prior_refs = _all_refs(
        prior.inferred_needs, list(prior.engagement_state.evidence), list(prior.progress.evidence)
    )
    new_refs = [ref for ref in current_refs if ref not in prior_refs]

    def trigger_for(candidate: InferredNeed | None, fallback: InferredNeed | None):
        if new_refs:
            return _validate_evidence(list(new_refs), known)
        source = candidate or fallback
        if source is not None:
            return _validate_evidence(list(source.evidence), known)
        return _validate_evidence([message_ref(scope.latest_user_message)], known)

    correction = is_correction_of_inference(scope.latest_user_message.text)

    for need_type in sorted(set(previous_by_type) - set(current_by_type), key=lambda n: n.value):
        previous = previous_by_type[need_type]
        history.append(
            InferenceRevision(
                previous_inference=previous,
                new_inference=None,
                trigger_evidence=trigger_for(None, previous),
                reason=(
                    "사용자가 이전 추정을 정정했다" if correction else "새 근거로 추정을 철회했다"
                ),
                revised_at=now,
            )
        )

    for need_type in sorted(set(current_by_type) - set(previous_by_type), key=lambda n: n.value):
        current = current_by_type[need_type]
        history.append(
            InferenceRevision(
                previous_inference=None,
                new_inference=current,
                trigger_evidence=trigger_for(current, None),
                reason=(
                    "사용자가 이전 추정을 정정했다" if correction else "새 근거로 추정을 추가했다"
                ),
                revised_at=now,
            )
        )

    for need_type in sorted(set(previous_by_type) & set(current_by_type), key=lambda n: n.value):
        previous = previous_by_type[need_type]
        current = current_by_type[need_type]
        if previous.confidence == current.confidence and list(previous.evidence) == list(
            current.evidence
        ):
            continue
        history.append(
            InferenceRevision(
                previous_inference=previous,
                new_inference=current,
                trigger_evidence=trigger_for(current, previous),
                reason="같은 니즈의 근거 또는 확신도가 바뀌었다",
                revised_at=now,
            )
        )
    return history


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def track(payload: ConversationInput, *, now: datetime | None = None) -> ConversationState:
    """대화 상태를 조립한다. 입력은 변경하지 않는다."""
    validate_input_integrity(payload)
    now = now or datetime.now().astimezone()
    known = _known_ids(payload)
    video_before = [evidence.model_dump(mode="json") for evidence in payload.video_evidence]
    loops_before = [loop.model_dump(mode="json") for loop in payload.open_loops]

    scope = build_scope(payload)
    baseline = build_style_baseline(scope.messages, scope.behavior_events)
    explicit_intent = detect_explicit_intent(scope.latest_user_message.text)

    engagement = _build_engagement(scope, baseline, now, known)
    needs = _build_needs(payload, scope, baseline, now, known)
    progress = _build_progress(scope, now, known)
    facts = _build_confirmed_facts(scope, known)
    all_loops, unresolved = _resolve_open_loops(payload, scope)

    all_refs = list(engagement.evidence) + list(progress.evidence)
    for need in needs:
        all_refs.extend(need.evidence)

    history = _build_history(payload, scope, needs, all_refs, now, known)

    primary, secondary = select_strategy(
        explicit_intent=explicit_intent,
        needs=needs,
        engagement=engagement,
        progress=progress,
        topic=payload.active_coaching_topic,
        has_any_evidence=bool(
            scope.behavior_events or scope.feedback_events or scope.video_evidence
        ),
    )

    state = ConversationState(
        explicit_intent=explicit_intent,
        active_coaching_topic=payload.active_coaching_topic,
        confirmed_user_facts=facts,
        style_baseline=baseline,
        inferred_needs=needs,
        engagement_state=engagement,
        progress=progress,
        open_loops=all_loops,
        unresolved_open_loops=unresolved,
        next_response_strategy=primary,
        secondary_strategy=secondary,
        selected_context_message_ids=_select_context_message_ids(payload, scope, all_refs),
        inference_history=history,
    )

    if video_before != [e.model_dump(mode="json") for e in payload.video_evidence]:
        raise VideoEvidenceMutationError("트래커가 입력 영상 근거를 변경했다")
    if loops_before != [loop.model_dump(mode="json") for loop in payload.open_loops]:
        raise VideoEvidenceMutationError("트래커가 입력 Open Loop 를 변경했다")
    return state
