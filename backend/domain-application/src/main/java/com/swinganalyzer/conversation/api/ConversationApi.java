package com.swinganalyzer.conversation.api;

import java.util.UUID;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.swinganalyzer.conversation.application.ConversationApplicationService;
import com.swinganalyzer.conversation.application.ConversationApplicationService.ChatResult;
import com.swinganalyzer.shared.api.ShotContextRequest;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

@RestController
@RequestMapping("/v1")
public class ConversationApi {

	private final ConversationApplicationService service;

	public ConversationApi(ConversationApplicationService service) {
		this.service = service;
	}

	@PostMapping("/chat")
	ChatResponse chat(@Valid @RequestBody ChatRequest request) {
		ChatResult result = service.chat(
				request.anonymousSessionId(),
				request.conversationId(),
				request.message(),
				request.context().toInternal());
		return new ChatResponse(result.conversationId(), result.reply());
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
