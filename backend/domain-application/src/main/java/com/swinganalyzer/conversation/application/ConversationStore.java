package com.swinganalyzer.conversation.application;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Map;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.swinganalyzer.analysis.application.model.AiProcessingContract.ShotContext;
import com.swinganalyzer.conversation.infrastructure.persistence.ChatMessageEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.ChatMessageJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.ConversationEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.ConversationJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.OwnerContextEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.OwnerContextJpaRepository;
import com.swinganalyzer.shared.error.PublicApiException;

@Service
public class ConversationStore {

	private final OwnerContextJpaRepository owners;
	private final ConversationJpaRepository conversations;
	private final ChatMessageJpaRepository messages;

	public ConversationStore(
			OwnerContextJpaRepository owners,
			ConversationJpaRepository conversations,
			ChatMessageJpaRepository messages) {
		this.owners = owners;
		this.conversations = conversations;
		this.messages = messages;
	}

	/**
	 * Ensures the owner and conversation exist, records the current context and the
	 * incoming user message, and returns the ids the context engine needs.
	 * Recent-dialogue selection is done separately by
	 * {@link ContextRetrievalService}.
	 */
	@Transactional
	public PreparedConversation prepareTextTurn(
			String anonymousSessionId,
			UUID requestedConversationId,
			String message,
			ShotContext context) {
		return prepareTextTurn(
				getOrCreateOwner(anonymousSessionId).id(), requestedConversationId, message, context);
	}

	@Transactional
	public PreparedConversation prepareTextTurn(
			UUID ownerContextId,
			UUID requestedConversationId,
			String message,
			ShotContext context) {
		ConversationEntity conversation = getOrCreateConversation(ownerContextId, requestedConversationId);
		conversation.updateContext(context.shotProfile(), context.club(), context.analysisGoal());
		ChatMessageEntity userMessage = messages.save(
				new ChatMessageEntity(conversation.id(), null, "user", message, null));
		return new PreparedConversation(conversation.id(), ownerContextId, userMessage.id());
	}

	@Transactional
	public void saveAssistant(
			UUID conversationId,
			String content,
			Map<String, Object> interactionMeta) {
		messages.save(new ChatMessageEntity(
				conversationId, null, "assistant", content, interactionMeta));
	}

	@Transactional
	public void saveAssistant(
			UUID conversationId,
			UUID analysisRunId,
			String content,
			Map<String, Object> interactionMeta) {
		messages.save(new ChatMessageEntity(
				conversationId, analysisRunId, "assistant", content, interactionMeta));
	}

	@Transactional(readOnly = true)
	public OwnerContextEntity findOwner(String anonymousSessionId) {
		return owners.findByAnonymousSessionHash(hashAnonymousSession(anonymousSessionId)).orElse(null);
	}

	public OwnerContextEntity getOrCreateOwner(String anonymousSessionId) {
		String hash = hashAnonymousSession(anonymousSessionId);
		return owners.findByAnonymousSessionHash(hash)
				.orElseGet(() -> owners.save(new OwnerContextEntity(hash)));
	}

	public ConversationEntity getOrCreateConversation(UUID ownerId, UUID requestedConversationId) {
		if (requestedConversationId == null) {
			return conversations.save(new ConversationEntity(ownerId));
		}
		return conversations.findByIdAndOwnerContextId(requestedConversationId, ownerId)
				.orElseThrow(() -> new PublicApiException(
						HttpStatus.NOT_FOUND, "Conversation was not found for this owner"));
	}

	static String hashAnonymousSession(String anonymousSessionId) {
		try {
			byte[] digest = MessageDigest.getInstance("SHA-256")
					.digest(anonymousSessionId.getBytes(StandardCharsets.UTF_8));
			return HexFormat.of().formatHex(digest);
		} catch (NoSuchAlgorithmException error) {
			throw new IllegalStateException("SHA-256 is unavailable", error);
		}
	}

	public record PreparedConversation(UUID conversationId, UUID ownerContextId, UUID userMessageId) {
	}
}
