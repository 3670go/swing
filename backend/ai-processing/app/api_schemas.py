import uuid
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field

from app.domain.models import CoachReply, ShotContext, VisionObservation


class ChatRequest(BaseModel):
    anonymous_session_id: str = Field(min_length=16, max_length=128)
    conversation_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=4000)
    context: ShotContext


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    reply: str


class AnalysisResponse(BaseModel):
    conversation_id: uuid.UUID
    analysis_run_id: uuid.UUID
    status: Literal["succeeded", "limited", "rejected"]
    observation: VisionObservation
    reply: CoachReply | None


class OpenAIFileReference(BaseModel):
    """Temporary conversation file reference injected by a Custom GPT Action."""

    name: str = Field(min_length=1, max_length=255)
    id: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=128)
    download_link: AnyHttpUrl


class ActionAnalyzeRequest(BaseModel):
    """JSON bridge from Custom GPT uploads to the existing media analyzer."""

    session_id: str = Field(min_length=16, max_length=128)
    openai_file_id_refs: list[OpenAIFileReference] = Field(
        min_length=1,
        max_length=10,
        alias="openaiFileIdRefs",
    )
    question: str = Field(default="", max_length=4000)
    context: ShotContext
    conversation_id: uuid.UUID | None = None


class HistoryItem(BaseModel):
    analysis_run_id: uuid.UUID
    status: str
    media_kind: str
    club: str
    camera_view: str
    created_at: str


class HistoryResponse(BaseModel):
    items: list[HistoryItem]
