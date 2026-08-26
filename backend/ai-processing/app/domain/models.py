from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AssessmentCategory = Literal[
    "impact_structure",
    "transition_sequence",
    "arm_body_space",
    "center_posture",
    "backswing",
    "tempo_shape",
]
EvidenceMode = Literal["text_only", "photo_limited", "video_ready"]
InviteMode = Literal[
    "none",
    "compare_good_bad",
    "locate_timing",
    "recall_specific_shot",
    "connect_body_feel",
    "follow_up_experiment",
]


class ShotContext(BaseModel):
    """User-selected context; never treated as video observation."""

    shot_profile: Literal["full_swing", "short_game"]
    club: str = Field(min_length=1, max_length=64)
    camera_view: Literal["face_on", "down_the_line"]
    handedness: Literal["right", "left"]
    analysis_goal: Literal["posture_correction", "shot_result", "comparison"]
    short_game_type: str | None = Field(default=None, max_length=64)
    video_type: str | None = Field(default=None, max_length=64)
    shot_result: str | None = Field(default=None, max_length=128)


class ObservationItem(BaseModel):
    """One direct, time-bounded visual observation candidate."""

    timestamp: str | None = None
    subject: str = Field(min_length=1, max_length=80)
    reference: str = Field(min_length=1, max_length=120)
    phase: str = Field(min_length=1, max_length=80)
    state: str = Field(min_length=1, max_length=300)
    assessment_category: AssessmentCategory
    confidence: float = Field(ge=0, le=1)


class VisionObservation(BaseModel):
    is_golf_media: bool
    golf_media_reason: str = Field(min_length=1, max_length=300)
    observations: list[ObservationItem] = Field(max_length=12)
    cannot_determine: list[str] = Field(max_length=12)

    @model_validator(mode="after")
    def require_observation_for_golf_media(self) -> "VisionObservation":
        if self.is_golf_media and not self.observations:
            raise ValueError("Golf media requires at least one direct observation")
        if not self.is_golf_media and self.observations:
            raise ValueError("Rejected non-golf media cannot contain golf observations")
        return self


class AssessmentFinding(BaseModel):
    """One priority-ranked interpretation anchored to direct observations."""

    category: AssessmentCategory
    observation_indexes: list[int] = Field(min_length=1, max_length=12)
    summary: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0, le=1)


class BaseAssessment(BaseModel):
    """Question-blind assessment frozen before user context is applied."""

    model_config = ConfigDict(frozen=True)

    primary_category: AssessmentCategory
    importance: Literal["high", "medium", "low"]
    findings: list[AssessmentFinding] = Field(min_length=1, max_length=12)
    cannot_determine: list[str] = Field(max_length=12)
    assessment_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class CoachContent(BaseModel):
    """Evidence-bounded coaching content that is never rendered directly."""

    evidence_mode: EvidenceMode
    direct_answer: str = Field(min_length=1, max_length=700)
    causal_chain: list[str] = Field(max_length=3)
    evidence_boundary: str = Field(min_length=1, max_length=300)
    cannot_determine: list[str] = Field(max_length=8)
    observation_indexes: list[int] = Field(max_length=12)
    base_assessment_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    single_change: str | None = Field(default=None, max_length=500)
    verification: str | None = Field(default=None, max_length=500)
    preserve_candidate: str | None = Field(default=None, max_length=220)
    preserve_topic: str | None = Field(default=None, max_length=80)
    follow_up_information_needed: str | None = Field(default=None, max_length=180)

    @model_validator(mode="after")
    def enforce_evidence_contract(self) -> "CoachContent":
        if self.evidence_mode == "text_only":
            if self.base_assessment_hash is not None or self.observation_indexes:
                raise ValueError("Text-only content cannot claim current media observations")
        elif self.base_assessment_hash is None or not self.observation_indexes:
            raise ValueError("Media content must reference its frozen base assessment")
        if (self.preserve_candidate is None) != (self.preserve_topic is None):
            raise ValueError("Preserve candidate and topic must be supplied together")
        return self


class ConversationReply(BaseModel):
    """Only these fields may be rendered in the chat surface."""

    message: str = Field(min_length=1, max_length=900)
    positive_feedback: str | None = Field(default=None, max_length=220)
    positive_topic: str | None = Field(default=None, max_length=80)
    follow_up_question: str | None = Field(default=None, max_length=180)
    question_topic: str | None = Field(default=None, max_length=80)
    invite_mode: InviteMode = "none"

    @model_validator(mode="after")
    def require_paired_optional_fields(self) -> "ConversationReply":
        if (self.positive_feedback is None) != (self.positive_topic is None):
            raise ValueError("Positive feedback and topic must be supplied together")
        if (self.follow_up_question is None) != (self.question_topic is None):
            raise ValueError("Follow-up question and topic must be supplied together")
        if self.follow_up_question is None and self.invite_mode != "none":
            raise ValueError("Invite mode requires a follow-up question")
        return self


class CoachReply(BaseModel):
    """Validated analysis bundle returned by media analysis."""

    base_assessment: BaseAssessment
    content: CoachContent
    conversation: ConversationReply
