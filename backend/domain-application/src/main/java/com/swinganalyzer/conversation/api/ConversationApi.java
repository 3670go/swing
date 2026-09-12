package com.swinganalyzer.conversation.api;

import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;

import com.swinganalyzer.conversation.application.ConversationApplicationService;
import com.swinganalyzer.conversation.application.ConversationApplicationService.ChatResult;
import com.swinganalyzer.conversation.application.ConversationHistoryService;
import com.swinganalyzer.conversation.application.ConversationHistoryService.ConversationHistory;
import com.swinganalyzer.conversation.application.OwnerAccountService;
import com.swinganalyzer.shared.api.ShotContextRequest;
import com.swinganalyzer.shared.error.PublicApiException;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

@RestController
@RequestMapping("/v1")
public class ConversationApi {

	private final ConversationApplicationService service;
	private final ConversationHistoryService history;
	private final OwnerAccountService owners;

	public ConversationApi(
			ConversationApplicationService service,
			ConversationHistoryService history,
			OwnerAccountService owners) {
		this.service = service;
		this.history = history;
		this.owners = owners;
	}

	@PostMapping("/chat")
	ChatResponse chat(
			@AuthenticationPrincipal Jwt jwt,
			@Valid @RequestBody ChatRequest request) {
		UUID ownerContextId = owners.resolve(
				request.anonymousSessionId(), jwt == null ? null : jwt.getSubject());
		ChatResult result = service.chat(
				ownerContextId,
				request.conversationId(),
				request.message(),
				request.context().toInternal());
		return new ChatResponse(result.conversationId(), result.reply());
	}

	@GetMapping("/conversations/latest")
	ConversationHistory latest(
			@AuthenticationPrincipal Jwt jwt,
			@RequestParam("anonymous_session_id") String anonymousSessionId) {
		validateSession(anonymousSessionId);
		UUID ownerContextId = owners.resolve(
				anonymousSessionId, jwt == null ? null : jwt.getSubject());
		return history.latest(ownerContextId);
	}

	private static void validateSession(String anonymousSessionId) {
		if (anonymousSessionId == null
				|| anonymousSessionId.length() < 16
				|| anonymousSessionId.length() > 128) {
			throw new PublicApiException(HttpStatus.UNPROCESSABLE_CONTENT, "INVALID_REQUEST");
		}
	}

	public record ChatRequest(
			@NotBlank @Size(min = 16, max = 128) String anonymousSessionId,
			UUID conversationId,
			@NotBlank @Size(max = 4000) String message,
			@Valid ShotContextRequest context) {
	}

	public record ChatResponse(UUID conversationId, String reply) {
	}
}
