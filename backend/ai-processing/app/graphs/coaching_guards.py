from typing import Any, Literal

from app.domain.analysis_policy import validate_media_content
from app.domain.models import BaseAssessment, CoachingTurnPlan, ContextPacket, VisionObservation

HIGH_RECOGNITION_INTENSITIES = frozenset({"PROGRESS_DECLARATION", "IDENTITY_CONNECTION"})
HIGH_EVIDENCE_PROGRESS_LEVELS = frozenset({"VIDEO_VERIFIED_PROGRESS", "MILESTONE_COMPLETED"})
CURRENT_OBSERVATION_SOURCES = frozenset({"OBSERVATION"})
VERIFIED_PROGRESS_SOURCES = frozenset({"OBSERVATION", "PROGRESS_EVENT", "ROADMAP_MILESTONE"})
TEXT_BLOCKED_PROGRESS_LEVELS = frozenset({"VIDEO_VERIFIED_PROGRESS", "MILESTONE_COMPLETED"})
TEXT_BLOCKED_ROADMAP_TRANSITIONS = frozenset({"MARK_VIDEO_VERIFIED_PROGRESS"})
VERIFIED_ROADMAP_TRANSITIONS = frozenset({"MARK_VIDEO_VERIFIED_PROGRESS", "COMPLETE"})
MAX_STATE_CANDIDATES_PER_TURN = 6


class CoachingGuardViolation(ValueError):
    """A coaching plan candidate exceeded deterministic evidence limits."""


def validate_text_turn_plan(plan: CoachingTurnPlan) -> None:
    content = plan.coach_content
    if content.evidence_mode != "text_only":
        raise CoachingGuardViolation("Text turn claimed current media evidence")
    if content.observation_indexes or content.base_assessment_hash is not None:
        raise CoachingGuardViolation("Text turn referenced media observation evidence")
    _validate_candidate_limits(plan)
    _validate_progress_references(plan)
    _validate_text_evidence_transitions(plan)
    _validate_recognition_intensity(plan, require_current_observation=False)


def validate_media_turn_plan(
    plan: CoachingTurnPlan,
    *,
    media_kind: Literal["photo", "video"],
    assessment: BaseAssessment,
    observation: VisionObservation,
) -> None:
    validate_media_content(
        plan.coach_content,
        media_kind=media_kind,
        assessment=assessment,
        observation_count=len(observation.observations),
    )
    _validate_candidate_limits(plan)
    _validate_progress_references(plan)
    _validate_media_evidence_transitions(plan)
    _validate_recognition_intensity(plan, require_current_observation=True)


def validate_rejected_without_plan(status: str, plan: CoachingTurnPlan | None) -> None:
    if status == "rejected" and plan is not None:
        raise CoachingGuardViolation("Rejected analysis cannot create coaching state candidates")


def selected_shot_context_only(packet: ContextPacket) -> dict[str, str]:
    """Return only fields allowed to reach blind visual observation."""
    context = packet.request_context.selected_shot_context
    return {
        "shot_profile": context.shot_profile,
        "camera_view": context.camera_view,
        "handedness": context.handedness,
    }


def _validate_candidate_limits(plan: CoachingTurnPlan) -> None:
    count = len(plan.roadmap_update_candidates)
    count += len(plan.user_context_fact_candidates)
    count += int(plan.problem_reframe_candidate is not None)
    count += int(plan.coaching_topic_candidate is not None)
    count += int(plan.progress_candidate is not None)
    count += int(plan.recognition_candidate is not None)
    count += int(plan.open_loop_candidate is not None)
    if count > MAX_STATE_CANDIDATES_PER_TURN:
        raise CoachingGuardViolation("Too many state candidates in one turn")


def _validate_progress_references(plan: CoachingTurnPlan) -> None:
    if plan.progress_candidate is not None and not plan.progress_candidate.evidence_references:
        raise CoachingGuardViolation("Progress candidate requires evidence references")
    for candidate in plan.roadmap_update_candidates:
        if not candidate.evidence_references:
            raise CoachingGuardViolation("Roadmap update candidate requires evidence references")
    if (
        plan.problem_reframe_candidate is not None
        and not plan.problem_reframe_candidate.evidence_references
    ):
        raise CoachingGuardViolation("Problem reframe candidate requires evidence references")


def _validate_text_evidence_transitions(plan: CoachingTurnPlan) -> None:
    progress = plan.progress_candidate
    if progress is not None and progress.progress_level in TEXT_BLOCKED_PROGRESS_LEVELS:
        raise CoachingGuardViolation("Text turn cannot create video verified progress")

    for candidate in plan.roadmap_update_candidates:
        if candidate.proposed_transition in TEXT_BLOCKED_ROADMAP_TRANSITIONS:
            raise CoachingGuardViolation("Text turn cannot create video verified roadmap progress")
        if candidate.proposed_transition == "COMPLETE" and not _has_verified_progress_reference(
            candidate.evidence_references
        ):
            raise CoachingGuardViolation("Roadmap completion requires verified progress evidence")


def _validate_media_evidence_transitions(plan: CoachingTurnPlan) -> None:
    progress = plan.progress_candidate
    if progress is not None:
        if (
            progress.progress_level == "VIDEO_VERIFIED_PROGRESS"
            and not _has_current_observation_reference(progress.evidence_references)
        ):
            raise CoachingGuardViolation(
                "Video verified progress requires current observation evidence"
            )
        if (
            progress.progress_level == "MILESTONE_COMPLETED"
            and not _has_verified_progress_reference(progress.evidence_references)
        ):
            raise CoachingGuardViolation("Milestone completion requires verified progress evidence")

    for candidate in plan.roadmap_update_candidates:
        if (
            candidate.proposed_transition == "MARK_VIDEO_VERIFIED_PROGRESS"
            and not _has_current_observation_reference(candidate.evidence_references)
        ):
            raise CoachingGuardViolation(
                "Video verified roadmap progress requires current observation evidence"
            )
        if candidate.proposed_transition == "COMPLETE" and not _has_verified_progress_reference(
            candidate.evidence_references
        ):
            raise CoachingGuardViolation("Roadmap completion requires verified progress evidence")


def _validate_recognition_intensity(
    plan: CoachingTurnPlan,
    *,
    require_current_observation: bool,
) -> None:
    recognition = plan.recognition_candidate
    if recognition is None:
        return
    if recognition.proposed_intensity not in HIGH_RECOGNITION_INTENSITIES:
        return
    progress = plan.progress_candidate
    if progress is None or progress.progress_level not in HIGH_EVIDENCE_PROGRESS_LEVELS:
        raise CoachingGuardViolation("Recognition intensity exceeds evidence level")
    if require_current_observation:
        if not _has_current_observation_reference(progress.evidence_references):
            raise CoachingGuardViolation(
                "Recognition intensity requires current observation evidence"
            )
        return
    if not _has_verified_progress_reference(progress.evidence_references):
        raise CoachingGuardViolation("Recognition intensity requires verified progress evidence")


def _has_current_observation_reference(evidence_references: list[Any]) -> bool:
    return any(
        _source_type(reference) in CURRENT_OBSERVATION_SOURCES for reference in evidence_references
    )


def _has_verified_progress_reference(evidence_references: list[Any]) -> bool:
    return any(
        _source_type(reference) in VERIFIED_PROGRESS_SOURCES for reference in evidence_references
    )


def _source_type(reference: Any) -> str | None:
    if isinstance(reference, dict):
        return reference.get("source_type")
    return getattr(reference, "source_type", None)
