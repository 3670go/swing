import logging
import secrets
import uuid
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.adapters.ffmpeg_frame_extractor import FfmpegFrameExtractor
from app.adapters.signed_url_media_reader import SignedUrlMediaReader
from app.config import Settings, get_settings
from app.internal_schemas import (
    InternalAnalysisRequest,
    InternalAnalysisResponse,
    InternalErrorResponse,
    InternalHealthResponse,
    InternalTextCoachingRequest,
    InternalTextCoachingResponse,
)
from app.llm import GeminiModelAdapter
from app.ports.media_reader import RemoteMediaReference
from app.services.internal_processing import (
    InternalAiProcessingService,
    InternalAnalysisCommand,
    InternalProcessingError,
    InternalTextCoachingCommand,
)

logger = logging.getLogger(__name__)


class InternalApiError(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        retryable: bool,
        request_id: uuid.UUID,
        status_code: int,
        analysis_run_id: uuid.UUID | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.request_id = request_id
        self.analysis_run_id = analysis_run_id
        self.status_code = status_code


@lru_cache(maxsize=1)
def get_internal_service() -> InternalAiProcessingService:
    settings = get_settings()
    model = GeminiModelAdapter(settings, max_attempts=1)
    return InternalAiProcessingService(
        settings=settings,
        model=model,
        media_reader=SignedUrlMediaReader(settings),
        frame_extractor=FfmpegFrameExtractor(),
    )


def require_internal_bearer(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    expected = settings.internal_api_token_value
    prefix = "Bearer "
    if (
        expected is None
        or authorization is None
        or not authorization.startswith(prefix)
        or not secrets.compare_digest(authorization[len(prefix) :], expected)
    ):
        raise InternalApiError(
            code="INTERNAL_AUTH_FAILED",
            message="Internal authentication failed",
            retryable=False,
            request_id=uuid.uuid4(),
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


def _processing_status(code: str) -> int:
    return {
        "MEDIA_TYPE_UNSUPPORTED": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        "MEDIA_UNAVAILABLE": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "MEDIA_DECODE_FAILED": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "REQUEST_CONTRACT_INVALID": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "ANALYSIS_CONTRACT_FAILED": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "COACHING_GUARD_REJECTED": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "MODEL_REQUEST_INVALID": status.HTTP_502_BAD_GATEWAY,
        "MODEL_OUTPUT_INVALID": status.HTTP_502_BAD_GATEWAY,
        "MODEL_RATE_LIMITED": status.HTTP_429_TOO_MANY_REQUESTS,
        "MODEL_AUTH_FAILED": status.HTTP_502_BAD_GATEWAY,
        "MODEL_PROVIDER_UNAVAILABLE": status.HTTP_502_BAD_GATEWAY,
        "MODEL_UNAVAILABLE": status.HTTP_502_BAD_GATEWAY,
        "MODEL_TIMEOUT": status.HTTP_504_GATEWAY_TIMEOUT,
    }.get(code, status.HTTP_500_INTERNAL_SERVER_ERROR)


def _error_response(error: InternalApiError) -> JSONResponse:
    body = InternalErrorResponse(
        code=error.code,
        message=str(error),
        retryable=error.retryable,
        request_id=error.request_id,
        analysis_run_id=error.analysis_run_id,
    )
    return JSONResponse(status_code=error.status_code, content=body.model_dump(mode="json"))


internal_app = FastAPI(
    title="Swing Analyzer Internal AI API",
    version="2.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@internal_app.exception_handler(InternalApiError)
async def handle_internal_api_error(_request: Request, error: InternalApiError) -> JSONResponse:
    return _error_response(error)


@internal_app.exception_handler(RequestValidationError)
async def handle_internal_validation_error(
    request: Request,
    _error: RequestValidationError,
) -> JSONResponse:
    logger.warning("Internal request validation failed path=%s", request.url.path)
    return _error_response(
        InternalApiError(
            code="REQUEST_CONTRACT_INVALID",
            message="Internal request validation failed",
            retryable=False,
            request_id=uuid.uuid4(),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    )


@internal_app.exception_handler(Exception)
async def handle_unexpected_internal_error(_request: Request, error: Exception) -> JSONResponse:
    request_id = uuid.uuid4()
    logger.exception("Unexpected internal API error request_id=%s", request_id, exc_info=error)
    return _error_response(
        InternalApiError(
            code="INTERNAL_ERROR",
            message="Internal AI processing failed",
            retryable=False,
            request_id=request_id,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    )


@internal_app.get("/health", response_model=InternalHealthResponse)
def internal_health(
    settings: Annotated[Settings, Depends(get_settings)],
    service: Annotated[InternalAiProcessingService, Depends(get_internal_service)],
) -> InternalHealthResponse:
    ready = service.is_model_configured and settings.internal_api_token_value is not None
    return InternalHealthResponse(
        status="ready" if ready else "degraded",
        model_configured=service.is_model_configured,
    )


@internal_app.post(
    "/v1/analyses",
    response_model=InternalAnalysisResponse,
    dependencies=[Depends(require_internal_bearer)],
)
async def internal_analyze(
    request: InternalAnalysisRequest,
    service: Annotated[InternalAiProcessingService, Depends(get_internal_service)],
) -> InternalAnalysisResponse:
    command = InternalAnalysisCommand(
        request_id=request.request_id,
        analysis_run_id=request.analysis_run_id,
        media=tuple(
            RemoteMediaReference(
                media_id=media.media_id,
                kind=media.kind,
                content_type=media.content_type,
                size_bytes=media.size_bytes,
                sha256=media.sha256,
                read_url=str(media.read_url),
            )
            for media in request.media
        ),
        context_packet=request.context_packet,
    )
    try:
        result = await service.analyze(command)
    except InternalProcessingError as error:
        raise InternalApiError(
            code=error.code,
            message=str(error),
            retryable=error.retryable,
            request_id=request.request_id,
            analysis_run_id=request.analysis_run_id,
            status_code=_processing_status(error.code),
        ) from error
    return InternalAnalysisResponse(
        request_id=request.request_id,
        analysis_run_id=request.analysis_run_id,
        status=result.status,
        observation=result.observation,
        base_assessment=result.base_assessment,
        coaching_turn_plan=result.coaching_turn_plan,
    )


@internal_app.post(
    "/v1/coaching/text",
    response_model=InternalTextCoachingResponse,
    dependencies=[Depends(require_internal_bearer)],
)
async def internal_text_coaching(
    request: InternalTextCoachingRequest,
    service: Annotated[InternalAiProcessingService, Depends(get_internal_service)],
) -> InternalTextCoachingResponse:
    command = InternalTextCoachingCommand(
        request_id=request.request_id,
        context_packet=request.context_packet,
    )
    try:
        plan = await service.coach_text(command)
    except InternalProcessingError as error:
        raise InternalApiError(
            code=error.code,
            message=str(error),
            retryable=error.retryable,
            request_id=request.request_id,
            status_code=_processing_status(error.code),
        ) from error
    return InternalTextCoachingResponse(request_id=request.request_id, coaching_turn_plan=plan)
