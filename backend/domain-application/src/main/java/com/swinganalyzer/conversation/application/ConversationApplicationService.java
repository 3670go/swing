package com.swinganalyzer.conversation.application;

import java.util.UUID;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import com.swinganalyzer.analysis.application.AiProcessingClient;
import com.swinganalyzer.analysis.application.AiProcessingClientException;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.TextCoachingRequest;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.TextCoachingResponse;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.ShotContext;
import com.swinganalyzer.conversation.application.ConversationRenderer.RenderedConversation;
import com.swinganalyzer.conversation.application.ConversationStore.PreparedConversation;
import com.swinganalyzer.shared.error.PublicApiException;

@Service
public class ConversationApplicationService {

	private final ConversationStore store;
	private final ObjectProvider<AiProcessingClient> aiClientProvider;
	private final ConversationRenderer renderer;

	public ConversationApplicationService(
			ConversationStore store,
			ObjectProvider<AiProcessingClient> aiClientProvider,
			ConversationRenderer renderer) {
		this.store = store;
		this.aiClientProvider = aiClientProvider;
		this.renderer = renderer;
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

		try {
			UUID requestId = UUID.randomUUID();
			TextCoachingResponse response = client.coachText(new TextCoachingRequest(
					requestId,
					message,
					context,
					prepared.history(),
					prepared.hasLatestAnalysis()));
			if (!requestId.equals(response.requestId())) {
				throw new PublicApiException(HttpStatus.BAD_GATEWAY, "INTERNAL_RESPONSE_ID_MISMATCH");
			}
			RenderedConversation rendered = renderer.render(response.coachContent());
			store.saveAssistant(prepared.conversationId(), rendered.chatText(), rendered.interactionMeta());
			return new ChatResult(prepared.conversationId(), rendered.chatText());
		} catch (AiProcessingClientException error) {
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
