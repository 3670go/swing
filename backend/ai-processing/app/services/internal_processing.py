import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from app.adapters.signed_url_media_reader import MediaReaderError
from app.config import Settings
from app.domain.models import BaseAssessment, CoachContent, ShotContext, VisionObservation
from app.graphs.runtime import (
    GraphContractError,
    build_analysis_content_graph,
    build_text_content_graph,
)
from app.llm import ModelAdapter, ModelCallError, ModelNotConfiguredError
from app.media_processing import MediaProcessingError
from app.ports.frame_extractor import FrameExtractor
from app.ports.media_reader import MediaReader, RemoteMediaReference


@dataclass(frozen=True)
class ConversationHistoryItem:
    role: Literal["user", "assistant"]
    content: str
    interaction_meta: dict[str, Any] | None

    def graph_value(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "interaction_meta": self.interaction_meta,
        }


@dataclass(frozen=True)
class InternalAnalysisCommand:
    request_id: UUID
    analysis_run_id: UUID
    media: tuple[RemoteMediaReference, ...]
    context: ShotContext
    user_question: str
    user_feel: str | None
    history: tuple[ConversationHistoryItem, ...]


@dataclass(frozen=True)
class InternalAnalysisResult:
    status: Literal["succeeded", "limited", "rejected"]
    observation: VisionObservation
    base_assessment: BaseAssessment | None
    coach_content: CoachContent | None


@dataclass(frozen=True)
class InternalTextCoachingCommand:
    request_id: UUID
    message: str
    context: ShotContext
    history: tuple[ConversationHistoryItem, ...]
    has_latest_analysis: bool


class InternalProcessingError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class InternalAiProcessingService:
    """Run AI content generation without product persistence or surface rendering."""

    def __init__(
        self,
        *,
        settings: Settings,
        model: ModelAdapter,
        media_reader: MediaReader,
        frame_extractor: FrameExtractor,
    ) -> None:
        self._settings = settings
        self._model = model
        self._media_reader = media_reader
        self._frame_extractor = frame_extractor
        self._analysis_graph = build_analysis_content_graph(model)
        self._text_graph = build_text_content_graph(model)

    @property
    def is_model_configured(self) -> bool:
        return self._model.is_configured

    async def analyze(self, command: InternalAnalysisCommand) -> InternalAnalysisResult:
        self._require_model()
        with tempfile.TemporaryDirectory(prefix="internal-swing-analysis-") as temp_directory:
            temp_dir = Path(temp_directory)
            try:
                downloaded = [
                    await self._media_reader.read(media, temp_dir) for media in command.media
                ]
                frame_paths: list[Path] = []
                for index, media in enumerate(downloaded, start=1):
                    if media.kind == "photo":
                        frame_paths.append(media.path)
                        continue
                    frame_directory = temp_dir / f"frames_{index:02d}"
                    frame_directory.mkdir()
                    frame_paths.extend(
                        await self._frame_extractor.extract(
                            media.path,
                            frame_directory,
                            self._settings.analysis_frame_count,
                        )
                    )
                question = self._coaching_question(command.user_question, command.user_feel)
                result = await self._analysis_graph.ainvoke(
                    {
                        "frame_paths": frame_paths,
                        "media_kind": (
                            "video"
                            if any(media.kind == "video" for media in downloaded)
                            else "photo"
                        ),
                        "context": command.context,
                        "question": question,
                        "history": [item.graph_value() for item in command.history],
                    }
                )
            except MediaReaderError as error:
                raise InternalProcessingError(error.code, str(error), retryable=False) from error
            except MediaProcessingError as error:
                raise InternalProcessingError(
                    "MEDIA_DECODE_FAILED",
                    "Media frame extraction failed",
                    retryable=False,
                ) from error
            except GraphContractError as error:
                raise InternalProcessingError(
                    "ANALYSIS_CONTRACT_FAILED",
                    "Analysis output violated the evidence contract",
                    retryable=False,
                ) from error
            except (ModelCallError, ModelNotConfiguredError) as error:
                raise self._model_error(error) from error

        if result["status"] == "rejected":
            return InternalAnalysisResult(
                status="rejected",
                observation=result["observation"],
                base_assessment=None,
                coach_content=None,
            )
        return InternalAnalysisResult(
            status=result["status"],
            observation=result["observation"],
            base_assessment=result["base_assessment"],
            coach_content=result["content"],
        )

    async def coach_text(self, command: InternalTextCoachingCommand) -> CoachContent:
        self._require_model()
        try:
            result = await self._text_graph.ainvoke(
                {
                    "message": command.message,
                    "context": command.context,
                    "history": [item.graph_value() for item in command.history],
                    "latest_analysis": {} if command.has_latest_analysis else None,
                }
            )
        except GraphContractError as error:
            raise InternalProcessingError(
                "ANALYSIS_CONTRACT_FAILED",
                "Coaching output violated the evidence contract",
                retryable=False,
            ) from error
        except (ModelCallError, ModelNotConfiguredError) as error:
            raise self._model_error(error) from error
        return result["content"]

    def _require_model(self) -> None:
        if not self._model.is_configured:
            raise InternalProcessingError(
                "MODEL_UNAVAILABLE",
                "AI model is not configured",
                retryable=False,
            )

    @staticmethod
    def _coaching_question(user_question: str, user_feel: str | None) -> str:
        question = user_question.strip()
        feel = (user_feel or "").strip()
        if not feel:
            return question
        if not question:
            return f"사용자 체감: {feel}"
        return f"{question}\n사용자 체감: {feel}"

    @staticmethod
    def _model_error(error: ModelCallError | ModelNotConfiguredError) -> InternalProcessingError:
        code = getattr(error, "error_code", "MODEL_UNAVAILABLE")
        if code == "MODEL_RATE_LIMITED":
            return InternalProcessingError(
                "MODEL_RATE_LIMITED",
                "AI model rate limit reached",
                retryable=True,
            )
        if code in {"MODEL_RESPONSE_INVALID", "MODEL_REQUEST_INVALID"}:
            return InternalProcessingError(
                "ANALYSIS_CONTRACT_FAILED",
                "AI model returned an invalid structured response",
                retryable=False,
            )
        return InternalProcessingError(
            "MODEL_UNAVAILABLE",
            "AI model request failed",
            retryable=True,
        )
