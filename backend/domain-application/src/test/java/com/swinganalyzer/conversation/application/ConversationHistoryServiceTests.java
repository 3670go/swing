package com.swinganalyzer.conversation.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import org.junit.jupiter.api.Test;

import com.swinganalyzer.conversation.infrastructure.persistence.ChatMessageEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.ChatMessageJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.ConversationEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.ConversationJpaRepository;

class ConversationHistoryServiceTests {

	@Test
	void restoresLatestOwnedConversationInChronologicalOrder() {
		UUID ownerId = UUID.randomUUID();
		ConversationEntity conversation = new ConversationEntity(ownerId);
		ChatMessageEntity user = new ChatMessageEntity(
				conversation.id(), null, "user", "당겨 치는 이유가 궁금해", null);
		ChatMessageEntity assistant = new ChatMessageEntity(
				conversation.id(), null, "assistant", "회전 순서를 확인해보세요.", null);
		ConversationJpaRepository conversations = mock(ConversationJpaRepository.class);
		ChatMessageJpaRepository messages = mock(ChatMessageJpaRepository.class);
		when(conversations.findFirstByOwnerContextIdOrderByUpdatedAtDesc(ownerId))
				.thenReturn(Optional.of(conversation));
		when(messages.findByConversationIdOrderBySequenceNumberDesc(any(), any()))
				.thenReturn(List.of(assistant, user));

		ConversationHistoryService.ConversationHistory restored =
				new ConversationHistoryService(conversations, messages).latest(ownerId);

		assertThat(restored.conversationId()).isEqualTo(conversation.id());
		assertThat(restored.messages())
				.extracting(ConversationHistoryService.MessageView::content)
				.containsExactly("당겨 치는 이유가 궁금해", "회전 순서를 확인해보세요.");
	}

	@Test
	void returnsEmptyHistoryWhenMemberHasNoConversation() {
		UUID ownerId = UUID.randomUUID();
		ConversationJpaRepository conversations = mock(ConversationJpaRepository.class);
		ChatMessageJpaRepository messages = mock(ChatMessageJpaRepository.class);
		when(conversations.findFirstByOwnerContextIdOrderByUpdatedAtDesc(ownerId))
				.thenReturn(Optional.empty());

		ConversationHistoryService.ConversationHistory restored =
				new ConversationHistoryService(conversations, messages).latest(ownerId);

		assertThat(restored.conversationId()).isNull();
		assertThat(restored.messages()).isEmpty();
	}
}
