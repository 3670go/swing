package com.swinganalyzer.conversation.application;

import java.util.UUID;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import com.swinganalyzer.analysis.application.AiProcessingClient;
import com.swinganalyzer.analysis.application.AiProcessingClientException;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.ContextPacket;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.InternalTextCoachingRequest;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.InternalTextCoachingResponse;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.ShotContext;
import com.swinganalyzer.conversation.application.ConversationRenderer.RenderedConversation;
import com.swinganalyzer.conversation.application.ConversationStore.PreparedConversation;
import com.swinganalyzer.shared.error.PublicApiException;

@Service
public class ConversationApplicationService {

	private final ConversationStore store;
	private final ObjectProvider<AiProcessingClient> aiClientProvider;
	private final ConversationRenderer renderer;
	private final ContextRetrievalService contextRetrieval;
	private final ContextPacketAssembler contextPacketAssembler;
	private final ContextSnapshotStore contextSnapshotStore;
	private final CoachingPlanApplicationService coachingPlanApplication;

	public ConversationApplicationService(
			ConversationStore store,
			ObjectProvider<AiProcessingClient> aiClientProvider,
			ConversationRenderer renderer,
			ContextRetrievalService contextRetrieval,
			ContextPacketAssembler contextPacketAssembler,
			ContextSnapshotStore contextSnapshotStore,
			CoachingPlanApplicationService coachingPlanApplication) {
		this.store = store;
		this.aiClientProvider = aiClientProvider;
		this.renderer = renderer;
		this.contextRetrieval = contextRetrieval;
		this.contextPacketAssembler = contextPacketAssembler;
		this.contextSnapshotStore = contextSnapshotStore;
		this.coachingPlanApplication = coachingPlanApplication;
	}

	public ChatResult chat(
			String anonymousSessionId,
			UUID conversationId,
			String message,
			ShotContext context) {
		AiProcessingClient client = aiClientProvider.getIfAvailable();
		if (client == null) {
			throw new PublicApiException(HttpStatus.SERVICE_UNAVAILABLE, "AI_PROCESSING_NOT_CONFIGURED");
		}
		PreparedConversation prepared = store.prepareTextTurn(
				anonymousSessionId, conversationId, message, context);

		UUID requestId = UUID.randomUUID();
		UUID snapshotId = UUID.randomUUID();
		ContextSelection selection = contextRetrieval.retrieve(
				prepared.ownerContextId(), prepared.conversationId(), context, message);
		ContextPacket contextPacket = contextPacketAssembler.assemble(
				snapshotId, message, context, false, selection);

		try {
			InternalTextCoachingResponse response = client.coachText(
					new InternalTextCoachingRequest(requestId, contextPacket));
			if (!requestId.equals(response.requestId())) {
				throw new PublicApiException(HttpStatus.BAD_GATEWAY, "INTERNAL_RESPONSE_ID_MISMATCH");
			}
			// The public response keeps its CoachContent shape. State candidates are
			// applied to Java-owned product state separately (Session 3) and never
			// leak internal schema into the user-facing reply.
			RenderedConversation rendered = renderer.render(
					response.coachingTurnPlan().coachContent());
			store.saveAssistant(prepared.conversationId(), rendered.chatText(), rendered.interactionMeta());
			contextSnapshotStore.save(
					snapshotId, requestId, prepared.ownerContextId(), prepared.conversationId(),
					null, selection, contextPacket);
			coachingPlanApplication.apply(new CoachingPlanApplicationService.ApplicationCommand(
					requestId, prepared.ownerContextId(), prepared.conversationId(), null,
					snapshotId, selection, response.coachingTurnPlan(), 0));
			return new ChatResult(prepared.conversationId(), rendered.chatText());
		} catch (AiProcessingClientException error) {
			// Python failure: no snapshot is written and no coaching state changes.
			throw new PublicApiException(mapStatus(error), error.code());
		}
	}

	private static HttpStatus mapStatus(AiProcessingClientException error) {
		return switch (error.code()) {
			case "MODEL_RATE_LIMITED" -> HttpStatus.TOO_MANY_REQUESTS;
			case "MODEL_TIMEOUT" -> HttpStatus.GATEWAY_TIMEOUT;
			case "ANALYSIS_CONTRACT_FAILED" -> HttpStatus.valueOf(422);
			default -> HttpStatus.BAD_GATEWAY;
		};
	}

	public record ChatResult(UUID conversationId, String reply) {
	}
}
