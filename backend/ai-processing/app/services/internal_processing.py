import logging
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

from app.adapters.signed_url_media_reader import MediaReaderError
from app.config import Settings
from app.domain.models import (
    BaseAssessment,
    CoachingTurnPlan,
    ContextPacket,
    VisionObservation,
)
from app.graphs.runtime import (
    GraphContractError,
    build_analysis_content_graph,
    build_text_content_graph,
    build_text_turn_plan,
)
from app.llm import ModelAdapter, ModelCallError, ModelNotConfiguredError
from app.media_processing import MediaProcessingError
from app.ports.frame_extractor import FrameExtractor
from app.ports.media_reader import MediaReader, RemoteMediaReference

logger = logging.getLogger(__name__)

COACHING_GRAPH_MARKERS = (
    "왜",
    "원인",
    "어떻게",
    "방법",
    "교정",
    "고쳐",
    "고치는",
    "분석",
    "진단",
    "비교",
    "차이",
    "맞아",
    "해야",
    "해도",
    "문제",
    "드릴",
    "연습법",
    "자세",
    "동작",
    "메커니즘",
    "매커니즘",
    "괜찮",
    "좋은 거",
    "좋은거",
)


def _is_conversation_turn(context_packet: ContextPacket) -> bool:
    """Keep broad or relational text in the one-call conversation path."""
    if context_packet.request_context.media_presence:
        return False
    message = re.sub(r"\s+", "", context_packet.request_context.user_message.casefold())
    return len(message) <= 80 and not any(marker in message for marker in COACHING_GRAPH_MARKERS)


@dataclass(frozen=True)
class InternalAnalysisCommand:
    request_id: UUID
    analysis_run_id: UUID
    media: tuple[RemoteMediaReference, ...]
    context_packet: ContextPacket


@dataclass(frozen=True)
class InternalAnalysisResult:
    status: Literal["succeeded", "limited", "rejected"]
    observation: VisionObservation
    base_assessment: BaseAssessment | None
    coaching_turn_plan: CoachingTurnPlan | None


@dataclass(frozen=True)
class InternalTextCoachingCommand:
    request_id: UUID
    context_packet: ContextPacket


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
                    media_id = command.media[index - 1].media_id
                    frame_directory = temp_dir / f"frames_{index:02d}_{media_id}"
                    frame_directory.mkdir()
                    frame_paths.extend(
                        await self._frame_extractor.extract(
                            media.path,
                            frame_directory,
                            self._settings.analysis_frame_count,
                        )
                    )
                result = await self._analysis_graph.ainvoke(
                    {
                        "frame_paths": frame_paths,
                        "media_kind": (
                            "video"
                            if any(media.kind == "video" for media in downloaded)
                            else "photo"
                        ),
                        "context_packet": command.context_packet,
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
                coaching_turn_plan=None,
            )
        return InternalAnalysisResult(
            status=result["status"],
            observation=result["observation"],
            base_assessment=result["base_assessment"],
            coaching_turn_plan=result["coaching_turn_plan"],
        )

    async def coach_text(self, command: InternalTextCoachingCommand) -> CoachingTurnPlan:
        try:
            if _is_conversation_turn(command.context_packet):
                generated = await self._model.compose_conversation_reply(
                    context_packet=command.context_packet,
                )
                return build_text_turn_plan(generated, command.context_packet)
            result = await self._text_graph.ainvoke(
                {
                    "context_packet": command.context_packet,
                }
            )
        except GraphContractError as error:
            logger.warning("Text coaching guard rejected request_id=%s", command.request_id)
            raise InternalProcessingError(
                "COACHING_GUARD_REJECTED",
                "Coaching output violated the evidence contract",
                retryable=False,
            ) from error
        except (ModelCallError, ModelNotConfiguredError) as error:
            mapped = self._model_error(error)
            logger.warning(
                "Text coaching model failed request_id=%s code=%s",
                command.request_id,
                mapped.code,
            )
            raise mapped from error
        return result["coaching_turn_plan"]

    def _require_model(self) -> None:
        if not self._model.is_configured:
            raise InternalProcessingError(
                "MODEL_UNAVAILABLE",
                "AI model is not configured",
                retryable=False,
            )

    @staticmethod
    def _model_error(error: ModelCallError | ModelNotConfiguredError) -> InternalProcessingError:
        code = getattr(error, "error_code", "MODEL_UNAVAILABLE")
        if code == "MODEL_RATE_LIMITED":
            return InternalProcessingError(
                "MODEL_RATE_LIMITED",
                "AI model rate limit reached",
                retryable=True,
            )
        if code == "MODEL_RESPONSE_INVALID":
            return InternalProcessingError(
                "MODEL_OUTPUT_INVALID",
                "AI model returned an invalid structured response",
                retryable=False,
            )
        if code == "MODEL_REQUEST_INVALID":
            return InternalProcessingError(
                "MODEL_REQUEST_INVALID",
                "AI model rejected the structured request",
                retryable=False,
            )
        if code == "MODEL_AUTH_FAILED":
            return InternalProcessingError(
                "MODEL_AUTH_FAILED",
                "AI model authentication failed",
                retryable=False,
            )
        if code == "MODEL_PROVIDER_UNAVAILABLE":
            return InternalProcessingError(
                "MODEL_PROVIDER_UNAVAILABLE",
                "AI model provider is unavailable",
                retryable=True,
            )
        if code == "MODEL_TIMEOUT":
            return InternalProcessingError(
                "MODEL_TIMEOUT",
                "AI model request timed out",
                retryable=True,
            )
        return InternalProcessingError(
            "MODEL_UNAVAILABLE",
            "AI model request failed",
            retryable=True,
        )
