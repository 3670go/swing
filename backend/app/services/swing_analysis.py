import asyncio
import logging
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import UploadFile

from app.config import Settings
from app.conversation_rendering import render_coach_reply
from app.database import Database
from app.domain.models import CoachReply, ShotContext, VisionObservation
from app.graphs.runtime import GraphContractError
from app.llm import ModelCallError, ModelNotConfiguredError
from app.media_processing import MediaProcessingError
from app.ports.frame_extractor import FrameExtractor
from app.ports.swing_analyzer import AiSwingAnalyzer, SwingAnalysisInput
from app.repositories.chat_messages import ChatMessageRepository
from app.repositories.owner_conversations import OwnerAccessError, OwnerConversationRepository
from app.repositories.swing_analyses import SwingAnalysisRepository
from app.services.analysis_failures import AnalysisFailurePolicy, AnalysisUseCaseError
from app.services.media_preparation import (
    MediaPreparationError,
    PreparedMedia,
    UploadedMediaPreparer,
)
from app.storage import StorageSigningError, SupabaseMediaStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StartSwingAnalysisResult:
    conversation_id: uuid.UUID
    analysis_run_id: uuid.UUID
    status: Literal["succeeded", "limited", "rejected"]
    observation: VisionObservation
    reply: CoachReply | None


class StartSwingAnalysisUseCase:
    """Coordinate one persisted media analysis without exposing orchestration to HTTP routes."""

    def __init__(
        self,
        *,
        settings: Settings,
        database: Database,
        owner_conversations: OwnerConversationRepository,
        messages: ChatMessageRepository,
        analyses: SwingAnalysisRepository,
        media_store: SupabaseMediaStore,
        analyzer: AiSwingAnalyzer,
        frame_extractor: FrameExtractor,
    ) -> None:
        self._settings = settings
        self._database = database
        self._owner_conversations = owner_conversations
        self._messages = messages
        self._analyses = analyses
        self._media_store = media_store
        self._analyzer = analyzer
        self._frame_extractor = frame_extractor
        self._media_preparer = UploadedMediaPreparer(settings)
        self._failure_policy = AnalysisFailurePolicy()

    async def execute(
        self,
        *,
        files: list[UploadFile],
        anonymous_session_hash: str,
        context: ShotContext,
        question: str,
        conversation_id: uuid.UUID | None,
    ) -> StartSwingAnalysisResult:
        if not self._analyzer.is_configured:
            raise AnalysisUseCaseError(
                "GEMINI_API_KEY is not configured",
                "not_configured",
            )
        run_id: uuid.UUID | None = None

        with tempfile.TemporaryDirectory(prefix="swing-analysis-") as temp_directory:
            temp_dir = Path(temp_directory)
            try:
                prepared_media = await self._media_preparer.prepare(files, temp_dir)
            except MediaPreparationError as error:
                raise self._failure_policy.from_error(error) from error
            media_kind = (
                "photo" if all(media.media_kind == "photo" for media in prepared_media) else "video"
            )

            try:
                with self._database.session() as session:
                    owner = self._owner_conversations.get_or_create_owner(
                        session,
                        anonymous_session_hash,
                    )
                    conversation = self._owner_conversations.get_or_create_conversation(
                        session,
                        owner=owner,
                        conversation_id=conversation_id,
                        context=context,
                    )
                    swing_session = self._analyses.create_swing_session(
                        session,
                        owner_id=owner.id,
                        conversation_id=conversation.id,
                        context=context,
                        question=question,
                    )
                    run = self._analyses.create_analysis_run(
                        session,
                        swing_session_id=swing_session.id,
                        conversation_id=conversation.id,
                        media_kind=media_kind,
                        model=self._settings.gemini_model,
                    )
                    self._messages.add_message(
                        session,
                        conversation_id=conversation.id,
                        role="user",
                        content=question.strip() or "전체 우선순위로 분석해줘",
                        analysis_run_id=run.id,
                    )
                    history = self._messages.recent_messages(session, conversation.id)
                    conversation_id = conversation.id
                    swing_session_id = swing_session.id
                    run_id = run.id
            except OwnerAccessError as error:
                raise self._failure_policy.from_error(error) from error

            uploaded_assets: list[tuple[uuid.UUID, str, PreparedMedia]] = []
            try:
                for media in prepared_media:
                    media_asset_id = uuid.uuid4()
                    storage_path = (
                        f"original-{media.media_kind}/{swing_session_id}/"
                        f"{media_asset_id}{media.path.suffix}"
                    )
                    await asyncio.to_thread(
                        self._media_store.upload,
                        storage_path,
                        media.path,
                        media.content_type,
                    )
                    uploaded_assets.append((media_asset_id, storage_path, media))

                with self._database.session() as session:
                    for media_asset_id, storage_path, media in uploaded_assets:
                        self._analyses.create_uploaded_media(
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
                        await self._frame_extractor.extract(
                            media.path,
                            frame_dir,
                            self._settings.analysis_frame_count,
                        )
                    )

                result = await self._analyzer.analyze(
                    SwingAnalysisInput(
                        frame_paths=frame_paths,
                        media_kind=media_kind,
                        context=context,
                        question=question.strip(),
                        history=history,
                    )
                )
                observation = result.observation
                reply = result.reply
                analysis_status = result.status
            except StorageSigningError as error:
                if uploaded_assets:
                    uploaded_paths = [storage_path for _, storage_path, _ in uploaded_assets]
                    try:
                        await asyncio.to_thread(self._media_store.remove_many, uploaded_paths)
                    except StorageSigningError:
                        logger.exception("Could not roll back partially uploaded media bundle")
                if run_id is not None:
                    with self._database.session() as session:
                        self._analyses.fail_analysis(session, run_id, "STORAGE_UNAVAILABLE")
                raise self._failure_policy.from_error(error) from error
            except MediaProcessingError as error:
                if run_id is not None:
                    with self._database.session() as session:
                        self._analyses.fail_analysis(session, run_id, "MEDIA_DECODE_FAILED")
                raise self._failure_policy.from_error(error) from error
            except (GraphContractError, ModelCallError, ModelNotConfiguredError) as error:
                error_code = getattr(error, "error_code", "MODEL_UNAVAILABLE")
                logger.exception("Media model request failed with %s", error_code)
                if run_id is not None:
                    with self._database.session() as session:
                        self._analyses.fail_analysis(session, run_id, error_code)
                raise self._failure_policy.from_error(error) from error

        with self._database.session() as session:
            self._analyses.finish_analysis(
                session,
                run_id=run_id,
                status=analysis_status,
                observation=observation,
                reply=reply,
            )
            if reply is not None:
                self._messages.add_message(
                    session,
                    conversation_id=conversation_id,
                    role="assistant",
                    content=render_coach_reply(reply),
                    analysis_run_id=run_id,
                    interaction_meta=result.interaction_meta,
                )

        return StartSwingAnalysisResult(
            conversation_id=conversation_id,
            analysis_run_id=run_id,
            status=analysis_status,
            observation=observation,
            reply=reply,
        )
