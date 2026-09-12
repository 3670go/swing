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
import com.swinganalyzer.analysis.application.model.AiProcessingContract.BaseAssessment;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.CoachContent;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.ContextPacket;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.InternalAnalysisRequest;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.InternalAnalysisResponse;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.MediaReference;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.ShotContext;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.VisionObservation;
import com.swinganalyzer.conversation.application.CoachingPlanApplicationService;
import com.swinganalyzer.conversation.application.ContextPacketAssembler;
import com.swinganalyzer.conversation.application.ContextRetrievalService;
import com.swinganalyzer.conversation.application.ContextSelection;
import com.swinganalyzer.conversation.application.ContextSnapshotStore;
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
	private final ContextRetrievalService contextRetrieval;
	private final ContextPacketAssembler contextPacketAssembler;
	private final ContextSnapshotStore contextSnapshotStore;
	private final CoachingPlanApplicationService coachingPlanApplication;
	private final ObjectMapper objectMapper;

	public AnalysisApplicationService(
			AnalysisStore store,
			ConversationStore conversationStore,
			MediaPreparationService mediaPreparation,
			MediaStorage mediaStorage,
			ObjectProvider<AiProcessingClient> aiClientProvider,
			ConversationRenderer renderer,
			ContextRetrievalService contextRetrieval,
			ContextPacketAssembler contextPacketAssembler,
			ContextSnapshotStore contextSnapshotStore,
			CoachingPlanApplicationService coachingPlanApplication,
			ObjectMapper objectMapper) {
		this.store = store;
		this.conversationStore = conversationStore;
		this.mediaPreparation = mediaPreparation;
		this.mediaStorage = mediaStorage;
		this.aiClientProvider = aiClientProvider;
		this.renderer = renderer;
		this.contextRetrieval = contextRetrieval;
		this.contextPacketAssembler = contextPacketAssembler;
		this.contextSnapshotStore = contextSnapshotStore;
		this.coachingPlanApplication = coachingPlanApplication;
		this.objectMapper = objectMapper;
	}

	public AnalysisResult analyze(
			List<MultipartFile> files,
			String anonymousSessionId,
			UUID conversationId,
			ShotContext context,
			String question) {
		return analyze(
				files, conversationStore.getOrCreateOwner(anonymousSessionId).id(), conversationId,
				context, question);
	}

	public AnalysisResult analyze(
			List<MultipartFile> files,
			UUID ownerContextId,
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
					ownerContextId, conversationId, context, question, mediaKind, null);
			List<String> uploadedPaths = new ArrayList<>();
			try {
				List<MediaReference> references = uploadAndReference(bundle.media(), started, uploadedPaths);
				UUID requestId = UUID.randomUUID();
				UUID snapshotId = UUID.randomUUID();
				ContextSelection selection = contextRetrieval.retrieve(
						started.ownerId(), started.conversationId(), context, question);
				ContextPacket contextPacket = contextPacketAssembler.assemble(
						snapshotId, question, context, true, selection);
				InternalAnalysisResponse response = aiClient.analyze(new InternalAnalysisRequest(
						requestId,
						started.runId(),
						references,
						contextPacket));
				if (!requestId.equals(response.requestId())
						|| !started.runId().equals(response.analysisRunId())) {
					throw new PublicApiException(HttpStatus.BAD_GATEWAY, "INTERNAL_RESPONSE_ID_MISMATCH");
				}
				// Consume coach_content, snapshot the used packet, then apply the plan
				// candidates to Java-owned product state (Session 3). The public
				// response keeps its existing shape.
				AnalysisResult result = finish(started, response);
				contextSnapshotStore.save(
						snapshotId, requestId, started.ownerId(), started.conversationId(),
						started.runId(), selection, contextPacket);
				coachingPlanApplication.apply(new CoachingPlanApplicationService.ApplicationCommand(
						requestId, started.ownerId(), started.conversationId(), started.runId(),
						snapshotId, started.userMessageId(), selection, response.coachingTurnPlan(),
						observationCount(response)));
				return result;
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
		return history(owner.id());
	}

	public List<HistoryItem> history(UUID ownerContextId) {
		return store.history(ownerContextId).stream()
				.map(AnalysisApplicationService::toHistoryItem)
				.toList();
	}

	public void delete(String anonymousSessionId, UUID runId) {
		OwnerContextEntity owner = conversationStore.findOwner(anonymousSessionId);
		if (owner == null) {
			throw new PublicApiException(HttpStatus.NOT_FOUND, "ANALYSIS_NOT_FOUND");
		}
		delete(owner.id(), runId);
	}

	public void delete(UUID ownerContextId, UUID runId) {
		DeletionTarget target = store.deletionTarget(ownerContextId, runId);
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

	private AnalysisResult finish(StartedAnalysis started, InternalAnalysisResponse response) {
		// Session 1: only coach_content is consumed. The Coaching Turn Plan state
		// candidates are intentionally ignored here; DB-backed application is
		// Session 2 scope. A rejected analysis carries a null turn plan.
		CoachContent coachContent = response.coachingTurnPlan() == null
				? null
				: response.coachingTurnPlan().coachContent();
		RenderedConversation rendered = coachContent == null
				? null
				: renderer.render(coachContent);
		AnalysisReply reply = response.baseAssessment() == null || coachContent == null
				? null
				: new AnalysisReply(
						response.baseAssessment(),
						coachContent,
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

	private static int observationCount(InternalAnalysisResponse response) {
		if (response.observation() == null || response.observation().observations() == null) {
			return 0;
		}
		return response.observation().observations().size();
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
					"REQUEST_CONTRACT_INVALID", "ANALYSIS_CONTRACT_FAILED", "COACHING_GUARD_REJECTED" ->
							HttpStatus.valueOf(422);
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
