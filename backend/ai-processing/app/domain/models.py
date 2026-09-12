from datetime import datetime
from typing import Literal
from uuid import UUID

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
EvidenceReferenceSource = Literal[
    "MESSAGE",
    "OBSERVATION",
    "ANALYSIS_EPISODE",
    "PROGRESS_EVENT",
    "ROADMAP_MILESTONE",
]
ProgressLevel = Literal[
    "USER_REPORTED_PROGRESS",
    "RESULT_REPEATED",
    "VIDEO_VERIFIED_PROGRESS",
    "MILESTONE_COMPLETED",
]
RecognitionIntensity = Literal[
    "ACKNOWLEDGEMENT",
    "SPECIFIC_RECOGNITION",
    "PROGRESS_DECLARATION",
    "IDENTITY_CONNECTION",
]
UserContextFactType = Literal[
    "BODY_TRAIT",
    "INJURY",
    "CURRENT_SWING_STYLE",
    "TARGET_SWING_STYLE",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ShotContext(StrictModel):
    """User-selected context; never treated as video observation."""

    shot_profile: Literal["full_swing", "short_game"]
    club: str = Field(min_length=1, max_length=64)
    camera_view: Literal["face_on", "down_the_line"]
    handedness: Literal["right", "left"]
    analysis_goal: Literal["posture_correction", "shot_result", "comparison"]
    short_game_type: str | None = Field(default=None, max_length=64)
    video_type: str | None = Field(default=None, max_length=64)
    shot_result: str | None = Field(default=None, max_length=128)


class CoachingScope(StrictModel):
    shot_profile: Literal["full_swing", "short_game"]
    club: str | None = Field(default=None, max_length=64)
    club_group: str | None = Field(default=None, max_length=64)
    short_game_type: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def require_club_or_group(self) -> "CoachingScope":
        if not self.club and not self.club_group:
            raise ValueError("Coaching scope requires club or club_group")
        return self


class RequestContext(StrictModel):
    user_message: str = Field(min_length=1, max_length=4000)
    user_feel: str | None = Field(default=None, max_length=1000)
    selected_shot_context: ShotContext
    media_presence: bool


class ActiveCoachingTopic(StrictModel):
    topic_id: UUID
    version: int = Field(ge=1)
    user_problem: str = Field(min_length=1, max_length=300)
    root_problem: str | None = Field(default=None, max_length=300)
    scope: CoachingScope
    active_hypothesis: str | None = Field(default=None, max_length=500)
    current_experiment: str | None = Field(default=None, max_length=500)
    carry_forward_feel: str | None = Field(default=None, max_length=300)


class RoadmapMilestoneSummary(StrictModel):
    milestone_id: UUID
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    evidence_level: Literal[
        "NOT_STARTED",
        "USER_REPORTED_PROGRESS",
        "RESULT_REPEATED",
        "VIDEO_VERIFIED_PROGRESS",
        "MILESTONE_COMPLETED",
    ]
    completion_condition: str = Field(min_length=1, max_length=500)


class RoadmapContext(StrictModel):
    roadmap_id: UUID
    version: int = Field(ge=1)
    target_swing: str = Field(min_length=1, max_length=500)
    current_milestone: RoadmapMilestoneSummary | None
    completed_milestones: list[RoadmapMilestoneSummary] = Field(max_length=10)
    next_completion_condition: str | None = Field(default=None, max_length=500)


class AnalysisEpisodeSummary(StrictModel):
    episode_id: UUID
    observation_summary: str = Field(min_length=1, max_length=700)
    evidence_level: Literal["TEXT_ONLY", "USER_REPORTED", "RESULT_REPEATED", "VIDEO_OBSERVED"]
    captured_at: datetime
    scope: CoachingScope


class UserContextFact(StrictModel):
    fact_id: UUID
    version: int = Field(ge=1)
    statement: str = Field(min_length=1, max_length=500)
    evidence_level: Literal[
        "USER_REPORTED",
        "RESULT_REPEATED",
        "VIDEO_OBSERVED",
        "REPEATED_OBSERVATION",
        "GLOBAL_CANDIDATE",
    ]
    scope: CoachingScope
    source_episode_ids: list[UUID] = Field(max_length=3)
    fact_type: UserContextFactType | None = None
    body_region: str | None = Field(default=None, max_length=64)
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def reject_duplicate_source_episode_ids(self) -> "UserContextFact":
        if len(self.source_episode_ids) != len(set(self.source_episode_ids)):
            raise ValueError("source_episode_ids must be unique")
        return self


class PendingOpenLoop(StrictModel):
    open_loop_id: UUID
    version: int = Field(ge=1)
    state: Literal["PENDING"]
    carry_forward_feel: str | None = Field(default=None, max_length=300)
    next_single_change: str = Field(min_length=1, max_length=500)
    next_verification: str = Field(min_length=1, max_length=500)
    predicted_result: str | None = Field(default=None, max_length=500)


class ProgressEventSummary(StrictModel):
    progress_event_id: UUID
    topic_id: UUID
    milestone_id: UUID | None
    progress_level: ProgressLevel
    user_signal: str = Field(min_length=1, max_length=500)


class RecognizedTopicSummary(StrictModel):
    topic_id: UUID
    milestone_version: int = Field(ge=1)
    recognized_at: datetime


class RecognitionContext(StrictModel):
    unrecognized_progress_events: list[ProgressEventSummary] = Field(max_length=10)
    recently_recognized_topics: list[RecognizedTopicSummary] = Field(max_length=10)
    last_roadmap_reveal_at: datetime | None = None


class InteractionMeta(StrictModel):
    response_mode: Literal["short", "standard", "deep"]
    positive_topic: str | None = Field(default=None, max_length=80)
    question_topic: str | None = Field(default=None, max_length=80)
    invite_mode: Literal[
        "none",
        "compare_good_bad",
        "locate_timing",
        "recall_specific_shot",
        "connect_body_feel",
        "follow_up_experiment",
    ]


class HistoryMessage(StrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)
    interaction_meta: InteractionMeta | None = None


class ContextPacket(StrictModel):
    context_snapshot_id: UUID
    context_snapshot_version: int = Field(ge=1)
    request_context: RequestContext
    active_coaching_topic: ActiveCoachingTopic | None
    roadmap_context: RoadmapContext | None
    recent_dialogue: list[HistoryMessage] = Field(max_length=12)
    relevant_analysis_episodes: list[AnalysisEpisodeSummary] = Field(max_length=3)
    relevant_user_context_facts: list[UserContextFact] = Field(max_length=12)
    pending_open_loop: PendingOpenLoop | None
    recognition_context: RecognitionContext


class ObservationItem(StrictModel):
    """One direct, time-bounded visual observation candidate."""

    timestamp: str | None = None
    subject: str = Field(min_length=1, max_length=80)
    reference: str = Field(min_length=1, max_length=120)
    phase: str = Field(min_length=1, max_length=80)
    state: str = Field(min_length=1, max_length=300)
    assessment_category: AssessmentCategory
    confidence: float = Field(ge=0, le=1)


class VisionObservation(StrictModel):
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


class AssessmentFinding(StrictModel):
    """One priority-ranked interpretation anchored to direct observations."""

    category: AssessmentCategory
    observation_indexes: list[int] = Field(min_length=1, max_length=12)
    summary: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0, le=1)


class BaseAssessment(StrictModel):
    """Question-blind assessment frozen before user context is applied."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    primary_category: AssessmentCategory
    importance: Literal["high", "medium", "low"]
    findings: list[AssessmentFinding] = Field(min_length=1, max_length=12)
    cannot_determine: list[str] = Field(max_length=12)
    assessment_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class CoachContent(StrictModel):
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


class EvidenceReference(StrictModel):
    source_type: EvidenceReferenceSource
    source_id: str = Field(min_length=1, max_length=80)


class ProblemReframeCandidate(StrictModel):
    previous_problem: str = Field(min_length=1, max_length=300)
    proposed_root_problem: str = Field(min_length=1, max_length=300)
    causal_explanation: str = Field(min_length=1, max_length=700)
    evidence_references: list[EvidenceReference] = Field(min_length=1, max_length=6)


class CoachingTopicCandidate(StrictModel):
    action: Literal["REFRAME_CURRENT", "CREATE_NEW", "ACTIVATE_EXISTING", "RESOLVE_CURRENT"]
    target_topic_id: UUID | None
    expected_version: int | None = Field(default=None, ge=1)
    scope: CoachingScope
    title: str = Field(min_length=1, max_length=200)


class UserContextFactCandidate(StrictModel):
    action: Literal["UPSERT", "REMOVE"]
    fact_type: UserContextFactType
    body_region: str | None = Field(default=None, max_length=64)
    statement: str = Field(min_length=1, max_length=500)
    scope: CoachingScope | None


class RoadmapUpdateCandidate(StrictModel):
    target_type: Literal["ROADMAP", "MILESTONE"]
    target_id: UUID | None
    expected_version: int | None = Field(default=None, ge=1)
    proposed_transition: Literal[
        "CREATE",
        "UPDATE",
        "MARK_USER_REPORTED_PROGRESS",
        "MARK_RESULT_REPEATED",
        "MARK_VIDEO_VERIFIED_PROGRESS",
        "COMPLETE",
    ]
    proposed_content: str | None = Field(default=None, max_length=500)
    evidence_references: list[EvidenceReference] = Field(min_length=1, max_length=6)


class ProgressCandidate(StrictModel):
    target_milestone_id: UUID
    expected_version: int = Field(ge=1)
    progress_level: ProgressLevel
    user_signal: str = Field(min_length=1, max_length=500)
    evidence_references: list[EvidenceReference] = Field(min_length=1, max_length=6)


class RecognitionCandidate(StrictModel):
    target: str = Field(min_length=1, max_length=200)
    proposed_intensity: RecognitionIntensity
    recognition_content: str = Field(min_length=1, max_length=500)


class OpenLoopCandidate(StrictModel):
    carry_forward_feel: str | None = Field(default=None, max_length=300)
    next_single_change: str = Field(min_length=1, max_length=500)
    next_verification: str = Field(min_length=1, max_length=500)
    completion_condition: str = Field(min_length=1, max_length=500)
    predicted_result: str | None = Field(default=None, max_length=500)
    question: str = Field(min_length=1, max_length=300)


class CoachingTurnPlan(StrictModel):
    coach_content: CoachContent
    problem_reframe_candidate: ProblemReframeCandidate | None
    coaching_topic_candidate: CoachingTopicCandidate | None
    user_context_fact_candidates: list[UserContextFactCandidate] = Field(
        default_factory=list,
        max_length=4,
    )
    roadmap_update_candidates: list[RoadmapUpdateCandidate] = Field(max_length=6)
    progress_candidate: ProgressCandidate | None
    recognition_candidate: RecognitionCandidate | None
    open_loop_candidate: OpenLoopCandidate | None
