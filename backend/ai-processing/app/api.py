import asyncio
import hashlib
import logging
import secrets
import uuid
from functools import lru_cache
from tempfile import SpooledTemporaryFile
from typing import Annotated, Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener
from urllib.request import Request as UrlRequest

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from starlette.datastructures import Headers

from app.adapters.ffmpeg_frame_extractor import FfmpegFrameExtractor
from app.adapters.langgraph_swing_analyzer import LangGraphSwingAnalyzer
from app.api_schemas import (
    ActionAnalyzeRequest,
    AnalysisResponse,
    ChatRequest,
    ChatResponse,
    HistoryItem,
    HistoryResponse,
)
from app.config import Settings, get_settings
from app.conversation_rendering import render_conversation_reply
from app.database import Database
from app.domain.models import ShotContext
from app.graphs.runtime import GraphContractError, build_text_graph
from app.llm import GeminiModelAdapter, ModelCallError, ModelNotConfiguredError
from app.repositories.chat_messages import ChatMessageRepository
from app.repositories.owner_conversations import OwnerAccessError, OwnerConversationRepository
from app.repositories.swing_analyses import SwingAnalysisRepository
from app.services.analysis_failures import AnalysisUseCaseError
from app.services.media_preparation import MediaPreparationError
from app.services.media_preparation import classify_media as classify_upload
from app.services.swing_analysis import StartSwingAnalysisUseCase
from app.storage import StorageSigningError, SupabaseMediaStore

CONTENT_TYPE_SUFFIXES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
}
logger = logging.getLogger(__name__)


class NoRedirectHandler(HTTPRedirectHandler):
    """Reject redirects so an approved download host cannot redirect to an internal address."""

    def redirect_request(
        self,
        req: UrlRequest,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def classify_media(content_type: str) -> tuple[str, str]:
    """Return the canonical media kind and suffix for a supported MIME type."""
    try:
        return classify_upload(content_type, settings)
    except MediaPreparationError as error:
        raise _analysis_http_exception(error.error_code, error.kind) from error


def _analysis_http_exception(error_code: str, failure_kind: str) -> HTTPException:
    status_by_kind = {
        "invalid_input": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "unsupported_media": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        "too_large": status.HTTP_413_CONTENT_TOO_LARGE,
        "not_found": status.HTTP_404_NOT_FOUND,
        "media_decode": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "dependency": status.HTTP_502_BAD_GATEWAY,
        "not_configured": status.HTTP_503_SERVICE_UNAVAILABLE,
    }
    return HTTPException(status_by_kind[failure_kind], error_code)


def anonymous_session_hash(anonymous_session_id: str) -> str:
    """Store a stable owner boundary without persisting the browser token."""
    return hashlib.sha256(anonymous_session_id.encode("utf-8")).hexdigest()


def validate_action_download_url(download_url: str, allowed_hosts: tuple[str, ...]) -> None:
    """Allow Custom GPT file downloads only from configured HTTPS hosts."""
    parsed = urlsplit(download_url)
    hostname = (parsed.hostname or "").lower()
    normalized_hosts = {host.lower() for host in allowed_hosts}
    if parsed.scheme != "https" or hostname not in normalized_hosts:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "ACTION_FILE_URL_UNTRUSTED",
        )


def verify_action_api_key(authorization: str | None, expected_api_key: str | None) -> None:
    """Require the bearer token configured in the Custom GPT Action."""
    if expected_api_key is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "GPT_ACTION_NOT_CONFIGURED")
    prefix = "Bearer "
    if authorization is None or not authorization.startswith(prefix):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "GPT_ACTION_UNAUTHORIZED")
    supplied_api_key = authorization[len(prefix) :]
    if not secrets.compare_digest(supplied_api_key, expected_api_key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "GPT_ACTION_UNAUTHORIZED")


def _download_action_upload(
    *,
    download_url: str,
    filename: str,
    content_type: str,
    allowed_hosts: tuple[str, ...],
    max_bytes: int | None,
) -> UploadFile:
    """Download one short-lived OpenAI file URL into a disk-backed UploadFile."""
    validate_action_download_url(download_url, allowed_hosts)
    file_object = SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b")  # noqa: SIM115
    request = UrlRequest(download_url, headers={"User-Agent": "swing-analyzer-action/0.1"})
    opener = build_opener(NoRedirectHandler())
    size = 0
    try:
        with opener.open(request, timeout=30) as response:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if max_bytes is not None and size > max_bytes:
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        "VIDEO_TOO_LARGE",
                    )
                file_object.write(chunk)
    except HTTPException:
        file_object.close()
        raise
    except (HTTPError, URLError, OSError) as error:
        file_object.close()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "ACTION_FILE_DOWNLOAD_FAILED",
        ) from error
    if size == 0:
        file_object.close()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "MEDIA_EMPTY")
    file_object.seek(0)
    return UploadFile(
        file=file_object,
        size=size,
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


@lru_cache(maxsize=1)
def get_database() -> Database:
    return Database(get_settings())


@lru_cache(maxsize=1)
def get_model() -> GeminiModelAdapter:
    return GeminiModelAdapter(get_settings())


@lru_cache(maxsize=1)
def get_media_store() -> SupabaseMediaStore:
    return SupabaseMediaStore(get_settings())


@lru_cache(maxsize=1)
def get_analysis_use_case() -> StartSwingAnalysisUseCase:
    return StartSwingAnalysisUseCase(
        settings=settings,
        database=get_database(),
        owner_conversations=owner_conversations,
        messages=messages,
        analyses=analyses,
        media_store=get_media_store(),
        analyzer=LangGraphSwingAnalyzer(get_model()),
        frame_extractor=FfmpegFrameExtractor(),
    )


owner_conversations = OwnerConversationRepository()
messages = ChatMessageRepository()
analyses = SwingAnalysisRepository()
settings: Settings = get_settings()
app = FastAPI(title="Swing Analyzer API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health() -> dict[str, Any]:
    """Return process readiness without exposing credentials."""
    return {
        "status": "ok",
        "database_configured": True,
        "storage_configured": True,
        "model_configured": get_model().is_configured,
        "model": settings.gemini_model,
    }


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Persist and answer one text-only chat turn."""
    model = get_model()
    if not model.is_configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "GEMINI_API_KEY is not configured")

    database = get_database()
    owner_hash = anonymous_session_hash(request.anonymous_session_id)
    try:
        with database.session() as session:
            owner = owner_conversations.get_or_create_owner(session, owner_hash)
            conversation = owner_conversations.get_or_create_conversation(
                session,
                owner=owner,
                conversation_id=request.conversation_id,
                context=request.context,
            )
            messages.add_message(
                session,
                conversation_id=conversation.id,
                role="user",
                content=request.message,
            )
            history = messages.recent_messages(session, conversation.id)
            latest_analysis = messages.latest_reply(session, conversation.id)
            conversation_id = conversation.id
    except OwnerAccessError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

    graph = build_text_graph(model)
    try:
        result = await graph.ainvoke(
            {
                "message": request.message,
                "context": request.context,
                "history": history,
                "latest_analysis": latest_analysis,
            }
        )
    except (GraphContractError, ModelCallError, ModelNotConfiguredError) as error:
        error_code = getattr(error, "error_code", "MODEL_UNAVAILABLE")
        logger.exception("Text model request failed with %s", error_code)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, error_code) from error

    reply = result["reply"]
    rendered = render_conversation_reply(reply)
    with database.session() as session:
        messages.add_message(
            session,
            conversation_id=conversation_id,
            role="assistant",
            content=rendered,
            interaction_meta=result.get("interaction_meta"),
        )
    return ChatResponse(conversation_id=conversation_id, reply=rendered)


@app.post("/v1/analyze", response_model=AnalysisResponse)
async def analyze(
    files: Annotated[list[UploadFile], File()],
    anonymous_session_id: Annotated[str, Form(min_length=16, max_length=128)],
    context_json: Annotated[str, Form()],
    question: Annotated[str, Form(max_length=4000)] = "",
    conversation_id: Annotated[uuid.UUID | None, Form()] = None,
) -> AnalysisResponse:
    """Store private media objects, observe them blind, then compose one validated reply."""
    try:
        context = ShotContext.model_validate_json(context_json)
    except ValidationError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "INVALID_SHOT_CONTEXT") from error

    try:
        result = await get_analysis_use_case().execute(
            files=files,
            anonymous_session_hash=anonymous_session_hash(anonymous_session_id),
            context=context,
            question=question,
            conversation_id=conversation_id,
        )
    except AnalysisUseCaseError as error:
        raise _analysis_http_exception(error.error_code, error.kind) from error
    return AnalysisResponse(
        conversation_id=result.conversation_id,
        analysis_run_id=result.analysis_run_id,
        status=result.status,
        observation=result.observation,
        reply=result.reply,
    )


@app.post("/v1/actions/analyze", response_model=AnalysisResponse)
async def analyze_from_gpt_action(
    request: ActionAnalyzeRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> AnalysisResponse:
    """Download Custom GPT conversation files and reuse the canonical analyzer."""
    verify_action_api_key(authorization, settings.action_api_key)
    uploads: list[UploadFile] = []
    try:
        for file_reference in request.openai_file_id_refs:
            content_type = file_reference.mime_type.lower()
            media_kind, _ = classify_media(content_type)
            upload = await asyncio.to_thread(
                _download_action_upload,
                download_url=str(file_reference.download_link),
                filename=file_reference.name,
                content_type=content_type,
                allowed_hosts=settings.gpt_action_file_hosts,
                max_bytes=settings.max_video_bytes if media_kind == "video" else None,
            )
            uploads.append(upload)
        return await analyze(
            files=uploads,
            anonymous_session_id=request.session_id,
            context_json=request.context.model_dump_json(),
            question=request.question,
            conversation_id=request.conversation_id,
        )
    finally:
        for upload in uploads:
            await upload.close()


def build_custom_gpt_action_schema(server_url: str) -> dict[str, Any]:
    """Build the exact OpenAPI contract required for Custom GPT file injection."""
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Swing Analyzer Custom GPT Action",
            "version": "0.1.0",
            "description": "Send uploaded golf videos or photos to the Swing Analyzer backend.",
        },
        "servers": [{"url": server_url.rstrip("/")}],
        "paths": {
            "/v1/actions/analyze": {
                "post": {
                    "operationId": "analyzeSwingMedia",
                    "summary": "Analyze uploaded golf swing media",
                    "description": (
                        "Use this whenever the user attaches one to ten golf swing MP4, MOV, "
                        "WEBM, JPG, PNG, or WEBP files. Pass every attached file through "
                        "openaiFileIdRefs. The API downloads the temporary file URLs, extracts "
                        "video frames, and returns the existing structured swing analysis."
                    ),
                    "security": [{"BearerAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": [
                                        "session_id",
                                        "openaiFileIdRefs",
                                        "context",
                                    ],
                                    "properties": {
                                        "session_id": {
                                            "type": "string",
                                            "minLength": 16,
                                            "maxLength": 128,
                                            "description": (
                                                "A stable opaque id for this GPT conversation. "
                                                "Generate it once and reuse it in later turns."
                                            ),
                                        },
                                        "openaiFileIdRefs": {
                                            "type": "array",
                                            "minItems": 1,
                                            "maxItems": 10,
                                            "items": {"type": "string"},
                                            "description": (
                                                "All golf swing videos or photos attached by the "
                                                "user in this conversation. Do not invent URLs."
                                            ),
                                        },
                                        "question": {
                                            "type": "string",
                                            "maxLength": 4000,
                                            "default": "",
                                            "description": "The user's question, copied verbatim.",
                                        },
                                        "conversation_id": {
                                            "type": "string",
                                            "format": "uuid",
                                            "description": (
                                                "The conversation_id returned by a previous call."
                                            ),
                                        },
                                        "context": {
                                            "type": "object",
                                            "required": [
                                                "shot_profile",
                                                "club",
                                                "camera_view",
                                                "handedness",
                                                "analysis_goal",
                                            ],
                                            "properties": {
                                                "shot_profile": {
                                                    "type": "string",
                                                    "enum": ["full_swing", "short_game"],
                                                },
                                                "club": {
                                                    "type": "string",
                                                    "minLength": 1,
                                                    "maxLength": 64,
                                                },
                                                "camera_view": {
                                                    "type": "string",
                                                    "enum": ["face_on", "down_the_line"],
                                                },
                                                "handedness": {
                                                    "type": "string",
                                                    "enum": ["right", "left"],
                                                },
                                                "analysis_goal": {
                                                    "type": "string",
                                                    "enum": [
                                                        "posture_correction",
                                                        "shot_result",
                                                        "comparison",
                                                    ],
                                                },
                                                "short_game_type": {"type": "string"},
                                                "video_type": {"type": "string"},
                                                "shot_result": {"type": "string"},
                                            },
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Completed structured swing analysis",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/ActionAnalysisResponse"
                                    }
                                }
                            },
                        },
                        "401": {"description": "Invalid Action bearer token"},
                        "422": {"description": "Invalid or unavailable media"},
                        "502": {"description": "Storage or model provider failed"},
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "ActionAnalysisResponse": {
                    "type": "object",
                    "required": [
                        "conversation_id",
                        "analysis_run_id",
                        "status",
                        "observation",
                    ],
                    "properties": {
                        "conversation_id": {
                            "type": "string",
                            "format": "uuid",
                        },
                        "analysis_run_id": {
                            "type": "string",
                            "format": "uuid",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["succeeded", "limited", "rejected"],
                        },
                        "observation": {"type": "object"},
                        "reply": {
                            "anyOf": [
                                {"type": "object"},
                                {"type": "null"},
                            ]
                        },
                    },
                }
            },
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                }
            },
        },
    }


@app.get("/v1/actions/openapi.json", include_in_schema=False)
def custom_gpt_action_schema(request: Request) -> dict[str, Any]:
    """Expose an importable Action schema with the deployed server URL."""
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    if host is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ACTION_SCHEMA_HOST_MISSING")
    hostname = host.split(":", 1)[0].lower()
    if scheme == "http" and hostname not in {"127.0.0.1", "localhost"}:
        scheme = "https"
    return build_custom_gpt_action_schema(f"{scheme}://{host}")


@app.get("/v1/history", response_model=HistoryResponse)
def history(
    anonymous_session_id: Annotated[str, Query(min_length=16, max_length=128)],
) -> HistoryResponse:
    database = get_database()
    owner_hash = anonymous_session_hash(anonymous_session_id)
    with database.session() as session:
        owner = owner_conversations.find_owner(session, owner_hash)
        if owner is None:
            return HistoryResponse(items=[])
        rows = analyses.history(session, owner_id=owner.id)
        items = [
            HistoryItem(
                analysis_run_id=run.id,
                status=run.status,
                media_kind=run.media_kind,
                club=swing_session.club,
                camera_view=swing_session.camera_view,
                created_at=run.created_at.isoformat(),
            )
            for run, swing_session in rows
        ]
    return HistoryResponse(items=items)


@app.delete("/v1/analysis/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analysis(
    run_id: uuid.UUID,
    anonymous_session_id: Annotated[str, Query(min_length=16, max_length=128)],
) -> None:
    """Hard-delete the Storage object and make derived analysis unavailable."""
    database = get_database()
    owner_hash = anonymous_session_hash(anonymous_session_id)
    with database.session() as session:
        owner = owner_conversations.find_owner(session, owner_hash)
        if owner is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "ANALYSIS_NOT_FOUND")
        owned = analyses.owned_run_with_assets(session, run_id=run_id, owner_id=owner.id)
        if owned is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "ANALYSIS_NOT_FOUND")
        _, assets = owned
        storage_paths = [asset.storage_path for asset in assets]
        media_asset_ids = [asset.id for asset in assets]

    try:
        await asyncio.to_thread(get_media_store().remove_many, storage_paths)
    except StorageSigningError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "STORAGE_UNAVAILABLE") from error

    with database.session() as session:
        analyses.mark_deleted(
            session,
            run_id=run_id,
            media_asset_ids=media_asset_ids,
        )
