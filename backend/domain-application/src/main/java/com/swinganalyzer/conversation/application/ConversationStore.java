package com.swinganalyzer.conversation.application;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.swinganalyzer.analysis.application.model.AiProcessingContract.HistoryMessage;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.InteractionMeta;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.ShotContext;
import com.swinganalyzer.analysis.infrastructure.persistence.AnalysisRunJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.ChatMessageEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.ChatMessageJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.ConversationEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.ConversationJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.OwnerContextEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.OwnerContextJpaRepository;
import com.swinganalyzer.shared.error.PublicApiException;

@Service
public class ConversationStore {

	private static final List<String> REPLY_STATUSES = List.of("succeeded", "limited");

	private final OwnerContextJpaRepository owners;
	private final ConversationJpaRepository conversations;
	private final ChatMessageJpaRepository messages;
	private final AnalysisRunJpaRepository analysisRuns;

	public ConversationStore(
			OwnerContextJpaRepository owners,
			ConversationJpaRepository conversations,
			ChatMessageJpaRepository messages,
			AnalysisRunJpaRepository analysisRuns) {
		this.owners = owners;
		this.conversations = conversations;
		this.messages = messages;
		this.analysisRuns = analysisRuns;
	}

	@Transactional
	public PreparedConversation prepareTextTurn(
			String anonymousSessionId,
			UUID requestedConversationId,
			String message,
			ShotContext context) {
		OwnerContextEntity owner = getOrCreateOwner(anonymousSessionId);
		ConversationEntity conversation = getOrCreateConversation(owner.id(), requestedConversationId);
		conversation.updateContext(context.shotProfile(), context.club(), context.analysisGoal());
		messages.save(new ChatMessageEntity(conversation.id(), null, "user", message, null));

		List<ChatMessageEntity> newestFirst = messages.findByConversationIdOrderBySequenceNumberDesc(
				conversation.id(), PageRequest.of(0, 12));
		List<HistoryMessage> history = new ArrayList<>();
		for (int index = newestFirst.size() - 1; index >= 0; index--) {
			history.add(toHistory(newestFirst.get(index)));
		}
		boolean hasLatestAnalysis = analysisRuns
				.findFirstByConversationIdAndStatusInOrderByCompletedAtDesc(
						conversation.id(), REPLY_STATUSES)
				.isPresent();
		return new PreparedConversation(conversation.id(), history, hasLatestAnalysis);
	}

	@Transactional
	public void saveAssistant(
			UUID conversationId,
			String content,
			Map<String, Object> interactionMeta) {
		messages.save(new ChatMessageEntity(
				conversationId, null, "assistant", content, interactionMeta));
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

	@Transactional(readOnly = true)
	public List<HistoryMessage> recentHistory(UUID conversationId, int limit) {
		List<ChatMessageEntity> newestFirst = messages.findByConversationIdOrderBySequenceNumberDesc(
				conversationId, PageRequest.of(0, limit));
		List<HistoryMessage> history = new ArrayList<>();
		for (int index = newestFirst.size() - 1; index >= 0; index--) {
			history.add(toHistory(newestFirst.get(index)));
		}
		return history;
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

	static String hashAnonymousSession(String anonymousSessionId) {
		try {
			byte[] digest = MessageDigest.getInstance("SHA-256")
					.digest(anonymousSessionId.getBytes(StandardCharsets.UTF_8));
			return HexFormat.of().formatHex(digest);
		} catch (NoSuchAlgorithmException error) {
			throw new IllegalStateException("SHA-256 is unavailable", error);
		}
	}

	private static HistoryMessage toHistory(ChatMessageEntity message) {
		Map<String, Object> meta = message.interactionMeta();
		InteractionMeta interactionMeta = meta == null ? null : new InteractionMeta(
				(String) meta.get("response_mode"),
				(String) meta.get("positive_topic"),
				(String) meta.get("question_topic"),
				(String) meta.get("invite_mode"));
		return new HistoryMessage(message.role(), message.content(), interactionMeta);
	}

	public record PreparedConversation(
			UUID conversationId,
			List<HistoryMessage> history,
			boolean hasLatestAnalysis) {
	}
}
