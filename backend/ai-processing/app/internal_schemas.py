from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, Field

from app.domain.models import BaseAssessment, CoachContent, ShotContext, VisionObservation

InternalErrorCode = Literal[
    "INTERNAL_AUTH_FAILED",
    "MEDIA_TYPE_UNSUPPORTED",
    "MEDIA_UNAVAILABLE",
    "MEDIA_DECODE_FAILED",
    "ANALYSIS_CONTRACT_FAILED",
    "MODEL_RATE_LIMITED",
    "MODEL_UNAVAILABLE",
    "MODEL_TIMEOUT",
    "INTERNAL_ERROR",
]


class InteractionMeta(BaseModel):
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


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)
    interaction_meta: InteractionMeta | None = None


class MediaReference(BaseModel):
    media_id: UUID
    kind: Literal["photo", "video"]
    content_type: str = Field(min_length=1, max_length=128)
    size_bytes: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    read_url: AnyHttpUrl


class InternalAnalysisRequest(BaseModel):
    request_id: UUID
    analysis_run_id: UUID
    media: list[MediaReference] = Field(min_length=1, max_length=10)
    shot_context: ShotContext
    user_question: str = Field(max_length=4000)
    user_feel: str | None = Field(default=None, max_length=1000)
    history: list[HistoryMessage] = Field(max_length=20)


class InternalAnalysisResponse(BaseModel):
    request_id: UUID
    analysis_run_id: UUID
    status: Literal["succeeded", "limited", "rejected"]
    observation: VisionObservation
    base_assessment: BaseAssessment | None
    coach_content: CoachContent | None


class InternalTextCoachingRequest(BaseModel):
    request_id: UUID
    message: str = Field(min_length=1, max_length=4000)
    shot_context: ShotContext
    history: list[HistoryMessage] = Field(max_length=20)
    has_latest_analysis: bool


class InternalTextCoachingResponse(BaseModel):
    request_id: UUID
    coach_content: CoachContent


class InternalHealthResponse(BaseModel):
    service: Literal["ai-processing"] = "ai-processing"
    status: Literal["ready", "degraded"]
    model_configured: bool


class InternalErrorResponse(BaseModel):
    code: InternalErrorCode
    message: str = Field(min_length=1, max_length=300)
    retryable: bool
    request_id: UUID
    analysis_run_id: UUID | None = None
