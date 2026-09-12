package com.swinganalyzer.conversation.application;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.swinganalyzer.conversation.application.ConversationHistoryService.ConversationHistory;
import com.swinganalyzer.conversation.application.ConversationHistoryService.MessageView;
import com.swinganalyzer.conversation.infrastructure.persistence.ChatMessageEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.ChatMessageJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.ConversationEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.ConversationJpaRepository;

@Service
public class ConversationHistoryService {

	private static final int MAX_RESTORED_MESSAGES = 100;

	private final ConversationJpaRepository conversations;
	private final ChatMessageJpaRepository messages;

	public ConversationHistoryService(
			ConversationJpaRepository conversations,
			ChatMessageJpaRepository messages) {
		this.conversations = conversations;
		this.messages = messages;
	}

	@Transactional(readOnly = true)
	public ConversationHistory latest(UUID ownerContextId) {
		ConversationEntity conversation = conversations
				.findFirstByOwnerContextIdOrderByUpdatedAtDesc(ownerContextId)
				.orElse(null);
		if (conversation == null) {
			return new ConversationHistory(null, List.of());
		}

		List<ChatMessageEntity> newestFirst = messages.findByConversationIdOrderBySequenceNumberDesc(
				conversation.id(), PageRequest.of(0, MAX_RESTORED_MESSAGES));
		List<ChatMessageEntity> oldestFirst = new ArrayList<>(newestFirst);
		java.util.Collections.reverse(oldestFirst);
		return new ConversationHistory(
				conversation.id(),
				oldestFirst.stream()
						.map(message -> new MessageView(message.id(), message.role(), message.content()))
						.toList());
	}

	public record MessageView(UUID messageId, String role, String content) {
	}

	public record ConversationHistory(UUID conversationId, List<MessageView> messages) {
	}
}
