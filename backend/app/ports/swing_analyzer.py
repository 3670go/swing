from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from app.domain.models import CoachReply, ShotContext, VisionObservation


@dataclass(frozen=True)
class SwingAnalysisInput:
    frame_paths: list[Path]
    media_kind: Literal["photo", "video"]
    context: ShotContext
    question: str
    history: list[dict[str, Any]]


@dataclass(frozen=True)
class SwingAnalysisResult:
    status: Literal["succeeded", "limited", "rejected"]
    observation: VisionObservation
    reply: CoachReply | None
    interaction_meta: dict[str, Any] | None


class AiSwingAnalyzer(Protocol):
    """Analyze prepared swing frames without exposing graph implementation details."""

    @property
    def is_configured(self) -> bool: ...

    async def analyze(self, analysis_input: SwingAnalysisInput) -> SwingAnalysisResult: ...
