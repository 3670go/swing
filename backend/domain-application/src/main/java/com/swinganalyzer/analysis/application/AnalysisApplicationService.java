package com.swinganalyzer.analysis.application;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import com.swinganalyzer.analysis.application.AnalysisStore.StartedAnalysis;
import com.swinganalyzer.analysis.application.AnalysisStore.DeletionTarget;
import com.swinganalyzer.analysis.application.AnalysisStore.HistoryEntry;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.AnalysisRequest;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.AnalysisResponse;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.BaseAssessment;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.CoachContent;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.MediaReference;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.ShotContext;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.VisionObservation;
import com.swinganalyzer.conversation.application.ConversationRenderer;
import com.swinganalyzer.conversation.application.ConversationRenderer.RenderedConversation;
import com.swinganalyzer.conversation.application.ConversationStore;
import com.swinganalyzer.media.application.MediaPreparationService;
import com.swinganalyzer.media.application.MediaStorage;
import com.swinganalyzer.media.application.MediaStorageException;
import com.swinganalyzer.media.application.PreparedMedia;
import com.swinganalyzer.media.application.PreparedMediaBundle;
import com.swinganalyzer.shared.error.PublicApiException;
import com.swinganalyzer.conversation.infrastructure.persistence.OwnerContextEntity;

import tools.jackson.databind.ObjectMapper;

@Service
public class AnalysisApplicationService {

	private static final Logger logger = LoggerFactory.getLogger(AnalysisApplicationService.class);

	private final AnalysisStore store;
	private final ConversationStore conversationStore;
	private final MediaPreparationService mediaPreparation;
	private final MediaStorage mediaStorage;
	private final ObjectProvider<AiProcessingClient> aiClientProvider;
	private final ConversationRenderer renderer;
	private final ObjectMapper objectMapper;

	public AnalysisApplicationService(
			AnalysisStore store,
			ConversationStore conversationStore,
			MediaPreparationService mediaPreparation,
			MediaStorage mediaStorage,
			ObjectProvider<AiProcessingClient> aiClientProvider,
			ConversationRenderer renderer,
			ObjectMapper objectMapper) {
		this.store = store;
		this.conversationStore = conversationStore;
		this.mediaPreparation = mediaPreparation;
		this.mediaStorage = mediaStorage;
		this.aiClientProvider = aiClientProvider;
		this.renderer = renderer;
		this.objectMapper = objectMapper;
	}

	public AnalysisResult analyze(
			List<MultipartFile> files,
			String anonymousSessionId,
			UUID conversationId,
			ShotContext context,
			String question) {
		AiProcessingClient aiClient = aiClientProvider.getIfAvailable();
		if (aiClient == null) {
			throw new PublicApiException(HttpStatus.SERVICE_UNAVAILABLE, "AI_PROCESSING_NOT_CONFIGURED");
		}

		try (PreparedMediaBundle bundle = mediaPreparation.prepare(files)) {
			String mediaKind = bundle.media().stream().allMatch(media -> "photo".equals(media.kind()))
					? "photo"
					: "video";
			StartedAnalysis started = store.start(
					anonymousSessionId, conversationId, context, question, mediaKind, null);
			List<String> uploadedPaths = new ArrayList<>();
			try {
				List<MediaReference> references = uploadAndReference(bundle.media(), started, uploadedPaths);
				UUID requestId = UUID.randomUUID();
				AnalysisResponse response = aiClient.analyze(new AnalysisRequest(
						requestId,
						started.runId(),
						references,
						context,
						question,
						null,
						conversationStore.recentHistory(started.conversationId(), 20)));
				if (!requestId.equals(response.requestId())
						|| !started.runId().equals(response.analysisRunId())) {
					throw new PublicApiException(HttpStatus.BAD_GATEWAY, "INTERNAL_RESPONSE_ID_MISMATCH");
				}
				return finish(started, response);
			} catch (AiProcessingClientException error) {
				store.fail(started.runId(), error.code());
				throw new PublicApiException(mapStatus(error), error.code());
			} catch (MediaStorageException error) {
				rollbackUploads(uploadedPaths);
				store.fail(started.runId(), error.code());
				throw mapStorageError(error);
			} catch (PublicApiException error) {
				rollbackUploads(uploadedPaths);
				store.fail(started.runId(), error.detail());
				throw error;
			}
		} catch (MediaStorageException error) {
			throw mapStorageError(error);
		}
	}

	public List<HistoryItem> history(String anonymousSessionId) {
		OwnerContextEntity owner = conversationStore.findOwner(anonymousSessionId);
		if (owner == null) {
			return List.of();
		}
		return store.history(owner.id()).stream()
				.map(AnalysisApplicationService::toHistoryItem)
				.toList();
	}

	public void delete(String anonymousSessionId, UUID runId) {
		OwnerContextEntity owner = conversationStore.findOwner(anonymousSessionId);
		if (owner == null) {
			throw new PublicApiException(HttpStatus.NOT_FOUND, "ANALYSIS_NOT_FOUND");
		}
		DeletionTarget target = store.deletionTarget(owner.id(), runId);
		if (target == null) {
			throw new PublicApiException(HttpStatus.NOT_FOUND, "ANALYSIS_NOT_FOUND");
		}
		List<String> paths = target.assets().stream().map(asset -> asset.storagePath()).toList();
		try {
			mediaStorage.deleteMany(paths);
		} catch (MediaStorageException error) {
			throw mapStorageError(error);
		}
		store.markDeleted(runId, target.assets().stream().map(asset -> asset.id()).toList());
	}

	private List<MediaReference> uploadAndReference(
			List<PreparedMedia> mediaItems,
			StartedAnalysis started,
			List<String> uploadedPaths) {
		List<MediaReference> references = new ArrayList<>();
		for (PreparedMedia media : mediaItems) {
			UUID mediaId = UUID.randomUUID();
			String storagePath = "original-%s/%s/%s%s".formatted(
					media.kind(), started.swingSessionId(), mediaId, media.suffix());
			mediaStorage.upload(storagePath, media);
			uploadedPaths.add(storagePath);
			store.saveUploadedAsset(
					mediaId,
					started.swingSessionId(),
					media.kind(),
					storagePath,
					media.sha256());
			references.add(new MediaReference(
					mediaId,
					media.kind(),
					media.contentType(),
					media.sizeBytes(),
					media.sha256(),
					mediaStorage.createSignedReadUrl(storagePath)));
		}
		return references;
	}

	private AnalysisResult finish(StartedAnalysis started, AnalysisResponse response) {
		RenderedConversation rendered = response.coachContent() == null
				? null
				: renderer.render(response.coachContent());
		AnalysisReply reply = response.baseAssessment() == null || response.coachContent() == null
				? null
				: new AnalysisReply(
						response.baseAssessment(),
						response.coachContent(),
						toConversationResponse(rendered));
		store.complete(
				started.runId(),
				response.status(),
				toMap(response.observation()),
				reply == null ? null : toMap(reply),
				rendered == null ? null : rendered.chatText(),
				rendered == null ? null : rendered.interactionMeta());
		return new AnalysisResult(
				started.conversationId(),
				started.runId(),
				response.status(),
				response.observation(),
				reply);
	}

	private void rollbackUploads(List<String> uploadedPaths) {
		if (uploadedPaths.isEmpty()) {
			return;
		}
		try {
			mediaStorage.deleteMany(uploadedPaths);
			store.markAssetsDeletedByStoragePaths(uploadedPaths);
		} catch (MediaStorageException rollbackError) {
			logger.error("Could not roll back uploaded media", rollbackError);
		}
	}

	@SuppressWarnings("unchecked")
	private Map<String, Object> toMap(Object value) {
		return objectMapper.convertValue(value, Map.class);
	}

	private static ConversationResponse toConversationResponse(RenderedConversation rendered) {
		return new ConversationResponse(
				rendered.message(),
				rendered.positiveFeedback(),
				rendered.positiveTopic(),
				rendered.followUpQuestion(),
				rendered.questionTopic(),
				rendered.inviteMode());
	}

	private static HistoryItem toHistoryItem(HistoryEntry entry) {
		return new HistoryItem(
				entry.run().id(),
				entry.run().status(),
				entry.run().mediaKind(),
				entry.swingSession().club(),
				entry.swingSession().cameraView(),
				entry.run().createdAt().toString());
	}

	private static PublicApiException mapStorageError(MediaStorageException error) {
		HttpStatus status = switch (error.code()) {
			case "MEDIA_EMPTY", "MEDIA_TYPE_UNSUPPORTED", "TOO_MANY_MEDIA_FILES", "VIDEO_TOO_LARGE" ->
					HttpStatus.valueOf(422);
			case "STORAGE_NOT_CONFIGURED" -> HttpStatus.SERVICE_UNAVAILABLE;
			default -> HttpStatus.BAD_GATEWAY;
		};
		return new PublicApiException(status, error.code());
	}

	private static HttpStatus mapStatus(AiProcessingClientException error) {
		return switch (error.code()) {
			case "MODEL_RATE_LIMITED" -> HttpStatus.TOO_MANY_REQUESTS;
			case "MODEL_TIMEOUT" -> HttpStatus.GATEWAY_TIMEOUT;
			case "MEDIA_TYPE_UNSUPPORTED", "MEDIA_UNAVAILABLE", "MEDIA_DECODE_FAILED",
					"ANALYSIS_CONTRACT_FAILED" -> HttpStatus.valueOf(422);
			default -> HttpStatus.BAD_GATEWAY;
		};
	}

	public record ConversationResponse(
			String message,
			String positiveFeedback,
			String positiveTopic,
			String followUpQuestion,
			String questionTopic,
			String inviteMode) {
	}

	public record AnalysisReply(
			BaseAssessment baseAssessment,
			CoachContent content,
			ConversationResponse conversation) {
	}

	public record AnalysisResult(
			UUID conversationId,
			UUID analysisRunId,
			String status,
			VisionObservation observation,
			AnalysisReply reply) {
	}

	public record HistoryItem(
			UUID analysisRunId,
			String status,
			String mediaKind,
			String club,
			String cameraView,
			String createdAt) {
	}
}
