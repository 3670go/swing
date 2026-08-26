import hashlib
import json
from typing import Literal

from app.domain.models import (
    AssessmentCategory,
    AssessmentFinding,
    BaseAssessment,
    CoachContent,
    VisionObservation,
)

FORBIDDEN_MEASUREMENT_TERMS = (
    "club path",
    "face angle",
    "face-to-path",
    "attack angle",
    "low point",
    "ground reaction force",
    "클럽 패스",
    "페이스 앵글",
    "어택 앵글",
    "로우 포인트",
    "지면반력",
    "°",
)
CATEGORY_PRIORITY: dict[AssessmentCategory, int] = {
    "impact_structure": 1,
    "transition_sequence": 2,
    "arm_body_space": 3,
    "center_posture": 4,
    "backswing": 5,
    "tempo_shape": 6,
}
PHOTO_UNSUPPORTED_CATEGORIES = frozenset({"transition_sequence", "tempo_shape"})


class AnalysisPolicyViolation(ValueError):
    """An analysis claim exceeds the available golf-media evidence."""


def validate_observation(
    observation: VisionObservation,
    media_kind: Literal["photo", "video"],
) -> None:
    """Reject direct observations that exceed the evidence contract."""
    combined = " ".join(item.state for item in observation.observations).lower()
    forbidden = [term for term in FORBIDDEN_MEASUREMENT_TERMS if term in combined]
    if forbidden:
        raise AnalysisPolicyViolation(
            f"2D observation contains forbidden measurement claims: {', '.join(forbidden)}"
        )
    if media_kind != "photo":
        return
    if len(observation.observations) > 4:
        raise AnalysisPolicyViolation("Photo observation exceeded the single-frame evidence limit")
    unsupported = {
        item.assessment_category
        for item in observation.observations
        if item.assessment_category in PHOTO_UNSUPPORTED_CATEGORIES
    }
    if unsupported:
        raise AnalysisPolicyViolation(
            "Photo observation claimed sequence-only categories: " + ", ".join(sorted(unsupported))
        )


def build_base_assessment(observation: VisionObservation) -> BaseAssessment:
    """Create the same base assessment for the same blind visual evidence."""
    grouped: dict[AssessmentCategory, list[tuple[int, str, float]]] = {}
    for index, item in enumerate(observation.observations):
        grouped.setdefault(item.assessment_category, []).append(
            (index, item.state, item.confidence)
        )

    ordered_categories = sorted(grouped, key=CATEGORY_PRIORITY.__getitem__)
    findings = [
        AssessmentFinding(
            category=category,
            observation_indexes=[item[0] for item in grouped[category]],
            summary=" ".join(item[1] for item in grouped[category]),
            confidence=sum(item[2] for item in grouped[category]) / len(grouped[category]),
        )
        for category in ordered_categories
    ]
    primary_category = ordered_categories[0]
    payload = {
        "primary_category": primary_category,
        "importance": _importance_for(primary_category),
        "findings": [finding.model_dump(mode="json") for finding in findings],
        "cannot_determine": observation.cannot_determine,
    }
    assessment_hash = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return BaseAssessment(**payload, assessment_hash=assessment_hash)


def validate_frozen_assessment(
    assessment: BaseAssessment,
    observation: VisionObservation,
) -> None:
    """Ensure question-blind evidence was not changed after its freeze boundary."""
    expected = build_base_assessment(observation)
    if assessment.assessment_hash != expected.assessment_hash:
        raise AnalysisPolicyViolation("Base assessment changed before the freeze boundary")


def validate_media_content(
    content: CoachContent,
    *,
    media_kind: Literal["photo", "video"],
    assessment: BaseAssessment,
    observation_count: int,
) -> None:
    """Ensure coaching content references only frozen, existing evidence."""
    expected_mode = "photo_limited" if media_kind == "photo" else "video_ready"
    if content.evidence_mode != expected_mode:
        raise AnalysisPolicyViolation("Media content used the wrong evidence mode")
    if content.base_assessment_hash != assessment.assessment_hash:
        raise AnalysisPolicyViolation("Media content changed the frozen base assessment")
    if any(index < 0 or index >= observation_count for index in content.observation_indexes):
        raise AnalysisPolicyViolation("Media content referenced a missing observation")
    if media_kind == "photo":
        boundary = " ".join([content.evidence_boundary, *content.cannot_determine]).lower()
        if not any(term in boundary for term in ("동작 순서", "템포", "전환")):
            raise AnalysisPolicyViolation(
                "Photo content omitted the motion-sequence evidence limit"
            )


def _importance_for(category: AssessmentCategory) -> Literal["high", "medium", "low"]:
    priority = CATEGORY_PRIORITY[category]
    if priority <= 2:
        return "high"
    if priority <= 4:
        return "medium"
    return "low"
