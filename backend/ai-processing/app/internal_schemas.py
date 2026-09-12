from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator

from app.domain.models import (
    BaseAssessment,
    CoachingTurnPlan,
    ContextPacket,
    HistoryMessage,
    InteractionMeta,
    ShotContext,
    VisionObservation,
)

InternalErrorCode = Literal[
    "INTERNAL_AUTH_FAILED",
    "MEDIA_TYPE_UNSUPPORTED",
    "MEDIA_UNAVAILABLE",
    "MEDIA_DECODE_FAILED",
    "REQUEST_CONTRACT_INVALID",
    "ANALYSIS_CONTRACT_FAILED",
    "COACHING_GUARD_REJECTED",
    "MODEL_REQUEST_INVALID",
    "MODEL_OUTPUT_INVALID",
    "MODEL_RATE_LIMITED",
    "MODEL_AUTH_FAILED",
    "MODEL_PROVIDER_UNAVAILABLE",
    "MODEL_UNAVAILABLE",
    "MODEL_TIMEOUT",
    "INTERNAL_ERROR",
]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MediaReference(StrictSchema):
    media_id: UUID
    kind: Literal["photo", "video"]
    content_type: str = Field(min_length=1, max_length=128)
    size_bytes: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    read_url: AnyHttpUrl


class InternalAnalysisRequest(StrictSchema):
    request_id: UUID
    analysis_run_id: UUID
    media: list[MediaReference] = Field(min_length=1, max_length=10)
    context_packet: ContextPacket

    @model_validator(mode="after")
    def require_media_presence(self) -> "InternalAnalysisRequest":
        if not self.context_packet.request_context.media_presence:
            raise ValueError("Analysis request requires media_presence=true")
        return self


class InternalAnalysisResponse(StrictSchema):
    request_id: UUID
    analysis_run_id: UUID
    status: Literal["succeeded", "limited", "rejected"]
    observation: VisionObservation
    base_assessment: BaseAssessment | None
    coaching_turn_plan: CoachingTurnPlan | None


class InternalTextCoachingRequest(StrictSchema):
    request_id: UUID
    context_packet: ContextPacket

    @model_validator(mode="after")
    def reject_media_presence(self) -> "InternalTextCoachingRequest":
        if self.context_packet.request_context.media_presence:
            raise ValueError("Text coaching request requires media_presence=false")
        return self


class InternalTextCoachingResponse(StrictSchema):
    request_id: UUID
    coaching_turn_plan: CoachingTurnPlan


class InternalHealthResponse(StrictSchema):
    service: Literal["ai-processing"] = "ai-processing"
    status: Literal["ready", "degraded"]
    model_configured: bool


class InternalErrorResponse(StrictSchema):
    code: InternalErrorCode
    message: str = Field(min_length=1, max_length=300)
    retryable: bool
    request_id: UUID
    analysis_run_id: UUID | None = None


__all__ = [
    "BaseAssessment",
    "CoachingTurnPlan",
    "ContextPacket",
    "HistoryMessage",
    "InteractionMeta",
    "InternalAnalysisRequest",
    "InternalAnalysisResponse",
    "InternalErrorResponse",
    "InternalHealthResponse",
    "InternalTextCoachingRequest",
    "InternalTextCoachingResponse",
    "MediaReference",
    "ShotContext",
    "VisionObservation",
]
