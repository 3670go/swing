package com.swinganalyzer.analysis.application;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.swinganalyzer.analysis.application.model.AiProcessingContract.ShotContext;
import com.swinganalyzer.analysis.infrastructure.persistence.AnalysisRunEntity;
import com.swinganalyzer.analysis.infrastructure.persistence.AnalysisRunJpaRepository;
import com.swinganalyzer.analysis.infrastructure.persistence.SwingSessionEntity;
import com.swinganalyzer.analysis.infrastructure.persistence.SwingSessionJpaRepository;
import com.swinganalyzer.conversation.application.ConversationStore;
import com.swinganalyzer.conversation.infrastructure.persistence.ChatMessageEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.ChatMessageJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.ConversationEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.OwnerContextEntity;
import com.swinganalyzer.media.infrastructure.persistence.MediaAssetEntity;
import com.swinganalyzer.media.infrastructure.persistence.MediaAssetJpaRepository;

@Service
public class AnalysisStore {

	private final ConversationStore conversationStore;
	private final SwingSessionJpaRepository swingSessions;
	private final AnalysisRunJpaRepository analysisRuns;
	private final MediaAssetJpaRepository mediaAssets;
	private final ChatMessageJpaRepository messages;

	public AnalysisStore(
			ConversationStore conversationStore,
			SwingSessionJpaRepository swingSessions,
			AnalysisRunJpaRepository analysisRuns,
			MediaAssetJpaRepository mediaAssets,
			ChatMessageJpaRepository messages) {
		this.conversationStore = conversationStore;
		this.swingSessions = swingSessions;
		this.analysisRuns = analysisRuns;
		this.mediaAssets = mediaAssets;
		this.messages = messages;
	}

	@Transactional
	public StartedAnalysis start(
			String anonymousSessionId,
			UUID requestedConversationId,
			ShotContext context,
			String question,
			String mediaKind,
			String model) {
		return start(
				conversationStore.getOrCreateOwner(anonymousSessionId).id(), requestedConversationId,
				context, question, mediaKind, model);
	}

	@Transactional
	public StartedAnalysis start(
			UUID ownerContextId,
			UUID requestedConversationId,
			ShotContext context,
			String question,
			String mediaKind,
			String model) {
		ConversationEntity conversation = conversationStore.getOrCreateConversation(
				ownerContextId, requestedConversationId);
		conversation.updateContext(context.shotProfile(), context.club(), context.analysisGoal());

		Map<String, Object> shotResult = context.shotResult() == null
				? null
				: Map.of("value", context.shotResult());
		SwingSessionEntity swingSession = swingSessions.save(new SwingSessionEntity(
				ownerContextId,
				conversation.id(),
				context.shotProfile(),
				context.club(),
				context.cameraView(),
				context.handedness(),
				question,
				null,
				shotResult,
				null));
		AnalysisRunEntity run = analysisRuns.save(new AnalysisRunEntity(
				swingSession.id(), conversation.id(), mediaKind, model));
		conversation.activateAnalysis(run.id());
		ChatMessageEntity userMessage = messages.save(new ChatMessageEntity(
				conversation.id(),
				run.id(),
				"user",
				question.isBlank() ? "전체 우선순위로 분석해줘" : question,
				null));
		return new StartedAnalysis(ownerContextId, conversation.id(), swingSession.id(), run.id(), userMessage.id());
	}

	@Transactional
	public void saveUploadedAsset(
			UUID mediaId,
			UUID swingSessionId,
			String kind,
			String storagePath,
			String sha256) {
		mediaAssets.save(new MediaAssetEntity(
				mediaId,
				swingSessionId,
				"original_" + kind,
				storagePath,
				sha256,
				"uploaded"));
	}

	@Transactional
	public void complete(
			UUID runId,
			String status,
			Map<String, Object> observation,
			Map<String, Object> reply,
			String assistantContent,
			Map<String, Object> interactionMeta) {
		AnalysisRunEntity run = analysisRuns.findById(runId).orElseThrow();
		run.complete(status, observation, reply);
		if (assistantContent != null) {
			messages.save(new ChatMessageEntity(
					run.conversationId(), run.id(), "assistant", assistantContent, interactionMeta));
		}
	}

	@Transactional
	public void fail(UUID runId, String errorCode) {
		analysisRuns.findById(runId).ifPresent(run -> run.fail(errorCode));
	}

	@Transactional(readOnly = true)
	public List<HistoryEntry> history(UUID ownerId) {
		return analysisRuns.findHistory(ownerId, PageRequest.of(0, 20)).stream()
				.map(run -> {
					SwingSessionEntity swing = swingSessions.findById(run.swingSessionId()).orElseThrow();
					return new HistoryEntry(run, swing);
				})
				.toList();
	}

	@Transactional(readOnly = true)
	public DeletionTarget deletionTarget(UUID ownerId, UUID runId) {
		AnalysisRunEntity run = analysisRuns.findOwnedRun(runId, ownerId).orElse(null);
		if (run == null) {
			return null;
		}
		List<MediaAssetEntity> assets = mediaAssets.findAllBySessionId(run.swingSessionId());
		return new DeletionTarget(run, assets);
	}

	@Transactional
	public void markDeleted(UUID runId, List<UUID> mediaIds) {
		analysisRuns.findById(runId).ifPresent(AnalysisRunEntity::delete);
		mediaAssets.findAllById(mediaIds).forEach(MediaAssetEntity::markDeleted);
	}

	@Transactional
	public void markAssetsDeletedByStoragePaths(List<String> storagePaths) {
		mediaAssets.findAllByStoragePathIn(storagePaths).forEach(MediaAssetEntity::markDeleted);
	}

	public record StartedAnalysis(
			UUID ownerId,
			UUID conversationId,
			UUID swingSessionId,
			UUID runId,
			UUID userMessageId) {
	}

	public record HistoryEntry(AnalysisRunEntity run, SwingSessionEntity swingSession) {
	}

	public record DeletionTarget(AnalysisRunEntity run, List<MediaAssetEntity> assets) {
	}
}
