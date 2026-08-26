import asyncio
import hashlib
import logging
import secrets
import tempfile
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import Annotated, Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener
from urllib.request import Request as UrlRequest

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy import select
from starlette.datastructures import Headers

from app.config import Settings, get_settings
from app.database import Database
from app.graphs.runtime import GraphContractError, build_analysis_graph, build_text_graph
from app.llm import GeminiModelAdapter, ModelCallError, ModelNotConfiguredError
from app.media_processing import MediaProcessingError, extract_video_frames
from app.models import OwnerContext
from app.repositories.chat_runtime import (
    ChatRuntimeRepository,
    OwnerAccessError,
)
from app.schemas import (
    ActionAnalyzeRequest,
    AnalysisResponse,
    ChatRequest,
    ChatResponse,
    CoachReply,
    ConversationReply,
    HistoryItem,
    HistoryResponse,
    ShotContext,
    VisionObservation,
)
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


@dataclass(frozen=True)
class PreparedMedia:
    """One validated upload saved in the request-scoped temporary directory."""

    path: Path
    content_type: str
    media_kind: str
    sha256: str


def classify_media(content_type: str) -> tuple[str, str]:
    """Return the canonical media kind and suffix for a supported MIME type."""
    normalized = content_type.lower()
    if normalized in settings.allowed_photo_content_types:
        return "photo", CONTENT_TYPE_SUFFIXES[normalized]
    if normalized in settings.allowed_video_content_types:
        return "video", CONTENT_TYPE_SUFFIXES[normalized]
    raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "MEDIA_TYPE_UNSUPPORTED")


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


def render_conversation_reply(reply: ConversationReply) -> str:
    parts = [reply.message.strip()]
    if reply.positive_feedback:
        parts.append(reply.positive_feedback.strip())
    if reply.follow_up_question:
        parts.append(reply.follow_up_question.strip())
    return "\n\n".join(parts)


def render_coach_reply(reply: CoachReply) -> str:
    return render_conversation_reply(reply.conversation)


@lru_cache(maxsize=1)
def get_database() -> Database:
    return Database(get_settings())


@lru_cache(maxsize=1)
def get_model() -> GeminiModelAdapter:
    return GeminiModelAdapter(get_settings())


@lru_cache(maxsize=1)
def get_media_store() -> SupabaseMediaStore:
    return SupabaseMediaStore(get_settings())


repository = ChatRuntimeRepository()
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
            owner = repository.get_or_create_owner(session, owner_hash)
            conversation = repository.get_or_create_conversation(
                session,
                owner=owner,
                conversation_id=request.conversation_id,
                context=request.context,
            )
            repository.add_message(
                session,
                conversation_id=conversation.id,
                role="user",
                content=request.message,
            )
            history = repository.recent_messages(session, conversation.id)
            latest_analysis = repository.latest_reply(session, conversation.id)
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
        repository.add_message(
            session,
            conversation_id=conversation_id,
            role="assistant",
            content=rendered,
            interaction_meta=result.get("interaction_meta"),
        )
    return ChatResponse(conversation_id=conversation_id, reply=rendered)


async def _save_upload(upload: UploadFile, target: Path, max_bytes: int | None) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with target.open("wb") as output:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if max_bytes is not None and size > max_bytes:
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "VIDEO_TOO_LARGE")
            digest.update(chunk)
            output.write(chunk)
    if size == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "MEDIA_EMPTY")
    return size, digest.hexdigest()


@app.post("/v1/analyze", response_model=AnalysisResponse)
async def analyze(
    files: Annotated[list[UploadFile], File()],
    anonymous_session_id: Annotated[str, Form(min_length=16, max_length=128)],
    context_json: Annotated[str, Form()],
    question: Annotated[str, Form(max_length=4000)] = "",
    conversation_id: Annotated[uuid.UUID | None, Form()] = None,
) -> AnalysisResponse:
    """Store private media objects, observe them blind, then compose one validated reply."""
    model = get_model()
    if not model.is_configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "GEMINI_API_KEY is not configured")
    try:
        context = ShotContext.model_validate_json(context_json)
    except ValidationError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "INVALID_SHOT_CONTEXT") from error

    if not files:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "MEDIA_EMPTY")
    classified_uploads = [
        (upload, (upload.content_type or "").lower(), *classify_media(upload.content_type or ""))
        for upload in files
    ]
    media_kind = (
        "photo"
        if all(upload_kind == "photo" for _, _, upload_kind, _ in classified_uploads)
        else "video"
    )
    database = get_database()
    owner_hash = anonymous_session_hash(anonymous_session_id)
    run_id: uuid.UUID | None = None

    with tempfile.TemporaryDirectory(prefix="swing-analysis-") as temp_directory:
        temp_dir = Path(temp_directory)
        prepared_media: list[PreparedMedia] = []
        for index, (upload, content_type, upload_kind, suffix) in enumerate(
            classified_uploads,
            start=1,
        ):
            media_path = temp_dir / f"original_{index:02d}{suffix}"
            _, sha256 = await _save_upload(
                upload,
                media_path,
                settings.max_video_bytes if upload_kind == "video" else None,
            )
            prepared_media.append(
                PreparedMedia(
                    path=media_path,
                    content_type=content_type,
                    media_kind=upload_kind,
                    sha256=sha256,
                )
            )

        try:
            with database.session() as session:
                owner = repository.get_or_create_owner(session, owner_hash)
                conversation = repository.get_or_create_conversation(
                    session,
                    owner=owner,
                    conversation_id=conversation_id,
                    context=context,
                )
                swing_session = repository.create_swing_session(
                    session,
                    owner_id=owner.id,
                    conversation_id=conversation.id,
                    context=context,
                    question=question,
                )
                run = repository.create_analysis_run(
                    session,
                    swing_session_id=swing_session.id,
                    conversation_id=conversation.id,
                    media_kind=media_kind,
                    model=settings.gemini_model,
                )
                repository.add_message(
                    session,
                    conversation_id=conversation.id,
                    role="user",
                    content=question.strip() or "전체 우선순위로 분석해줘",
                    analysis_run_id=run.id,
                )
                history = repository.recent_messages(session, conversation.id)
                conversation_id = conversation.id
                swing_session_id = swing_session.id
                run_id = run.id
        except OwnerAccessError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

        uploaded_assets: list[tuple[uuid.UUID, str, PreparedMedia]] = []
        try:
            for media in prepared_media:
                media_asset_id = uuid.uuid4()
                storage_path = (
                    f"original-{media.media_kind}/{swing_session_id}/"
                    f"{media_asset_id}{media.path.suffix}"
                )
                await asyncio.to_thread(
                    get_media_store().upload,
                    storage_path,
                    media.path,
                    media.content_type,
                )
                uploaded_assets.append((media_asset_id, storage_path, media))

            with database.session() as session:
                for media_asset_id, storage_path, media in uploaded_assets:
                    repository.create_uploaded_media(
                        session,
                        media_asset_id=media_asset_id,
                        swing_session_id=swing_session_id,
                        media_kind=media.media_kind,
                        storage_path=storage_path,
                        sha256=media.sha256,
                    )

            frame_paths: list[Path] = []
            for index, media in enumerate(prepared_media, start=1):
                if media.media_kind == "photo":
                    frame_paths.append(media.path)
                    continue
                frame_dir = temp_dir / f"frames_{index:02d}"
                frame_dir.mkdir()
                frame_paths.extend(
                    await asyncio.to_thread(
                        extract_video_frames,
                        media.path,
                        frame_dir,
                        settings.analysis_frame_count,
                    )
                )

            graph = build_analysis_graph(model)
            result = await graph.ainvoke(
                {
                    "frame_paths": frame_paths,
                    "media_kind": media_kind,
                    "context": context,
                    "question": question.strip(),
                    "history": history,
                }
            )
            observation: VisionObservation = result["observation"]
            reply: CoachReply | None = result.get("reply")
            analysis_status: str = result["status"]
        except StorageSigningError as error:
            if uploaded_assets:
                uploaded_paths = [storage_path for _, storage_path, _ in uploaded_assets]
                try:
                    await asyncio.to_thread(get_media_store().remove_many, uploaded_paths)
                except StorageSigningError:
                    logger.exception("Could not roll back partially uploaded media bundle")
            if run_id is not None:
                with database.session() as session:
                    repository.fail_analysis(session, run_id, "STORAGE_UNAVAILABLE")
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "STORAGE_UNAVAILABLE") from error
        except MediaProcessingError as error:
            if run_id is not None:
                with database.session() as session:
                    repository.fail_analysis(session, run_id, "MEDIA_DECODE_FAILED")
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "MEDIA_DECODE_FAILED"
            ) from error
        except (GraphContractError, ModelCallError, ModelNotConfiguredError) as error:
            error_code = getattr(error, "error_code", "MODEL_UNAVAILABLE")
            logger.exception("Media model request failed with %s", error_code)
            if run_id is not None:
                with database.session() as session:
                    repository.fail_analysis(session, run_id, error_code)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, error_code) from error

    with database.session() as session:
        repository.finish_analysis(
            session,
            run_id=run_id,
            status=analysis_status,
            observation=observation,
            reply=reply,
        )
        if reply is not None:
            repository.add_message(
                session,
                conversation_id=conversation_id,
                role="assistant",
                content=render_coach_reply(reply),
                analysis_run_id=run_id,
                interaction_meta=result.get("interaction_meta"),
            )

    return AnalysisResponse(
        conversation_id=conversation_id,
        analysis_run_id=run_id,
        status=analysis_status,
        observation=observation,
        reply=reply,
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
        owner = session.scalar(
            select(OwnerContext).where(OwnerContext.anonymous_session_hash == owner_hash)
        )
        if owner is None:
            return HistoryResponse(items=[])
        rows = repository.history(session, owner_id=owner.id)
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
        owner = session.scalar(
            select(OwnerContext).where(OwnerContext.anonymous_session_hash == owner_hash)
        )
        if owner is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "ANALYSIS_NOT_FOUND")
        owned = repository.owned_run_with_assets(session, run_id=run_id, owner_id=owner.id)
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
        repository.mark_deleted(
            session,
            run_id=run_id,
            media_asset_ids=media_asset_ids,
        )
