package com.swinganalyzer.shared.persistence;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.domain.PageRequest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

import com.swinganalyzer.analysis.infrastructure.persistence.AnalysisRunEntity;
import com.swinganalyzer.analysis.infrastructure.persistence.AnalysisRunJpaRepository;
import com.swinganalyzer.analysis.infrastructure.persistence.SwingSessionEntity;
import com.swinganalyzer.analysis.infrastructure.persistence.SwingSessionJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.ChatMessageEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.ChatMessageJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.ConversationEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.ConversationJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.OwnerContextEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.OwnerContextJpaRepository;

import jakarta.persistence.EntityManager;

@SpringBootTest(properties = {
		"spring.datasource.url=jdbc:h2:mem:repositories;MODE=PostgreSQL;DB_CLOSE_DELAY=-1",
		"spring.datasource.username=sa",
		"spring.datasource.password=",
		"spring.jpa.hibernate.ddl-auto=create-drop",
		"spring.flyway.enabled=false"
})
@Transactional
class ProductRepositoryIntegrationTests {

	@Autowired
	private OwnerContextJpaRepository owners;

	@Autowired
	private ConversationJpaRepository conversations;

	@Autowired
	private SwingSessionJpaRepository swingSessions;

	@Autowired
	private AnalysisRunJpaRepository analysisRuns;

	@Autowired
	private ChatMessageJpaRepository chatMessages;

	@Autowired
	private JdbcTemplate jdbcTemplate;

	@Autowired
	private EntityManager entityManager;

	@Test
	void persistsOwnerConversationAndHistoryUnderOneOwner() {
		OwnerContextEntity owner = owners.saveAndFlush(new OwnerContextEntity("anonymous-hash"));
		ConversationEntity conversation = conversations.saveAndFlush(new ConversationEntity(owner.id()));
		conversation.updateContext("full_swing", "7_iron", "posture_correction");

		SwingSessionEntity swingSession = swingSessions.saveAndFlush(new SwingSessionEntity(
				owner.id(), conversation.id(), "full_swing", "7_iron", "dtl", "right",
				"왜 당겨 치나요?", null, Map.of("value", "pull"), null));
		AnalysisRunEntity run = analysisRuns.saveAndFlush(new AnalysisRunEntity(
				swingSession.id(), conversation.id(), "video", "contract-test-model"));
		conversation.activateAnalysis(run.id());

		assertThat(analysisRuns.findHistory(owner.id(), PageRequest.of(0, 20)))
				.extracting(AnalysisRunEntity::id)
				.containsExactly(run.id());
		assertThat(analysisRuns.findOwnedRun(run.id(), owner.id())).isPresent();
	}

	@Test
	void returnsRecentMessagesNewestFirstForPolicyInput() {
		OwnerContextEntity owner = owners.saveAndFlush(new OwnerContextEntity("message-owner"));
		ConversationEntity conversation = conversations.saveAndFlush(new ConversationEntity(owner.id()));
		chatMessages.saveAndFlush(new ChatMessageEntity(
				conversation.id(), null, "user", "첫 질문", null));
		chatMessages.saveAndFlush(new ChatMessageEntity(
				conversation.id(), null, "assistant", "첫 답변", Map.of("asked_follow_up", true)));
		jdbcTemplate.update("update chat_messages set sequence_number = 1 where content = ?", "첫 질문");
		jdbcTemplate.update("update chat_messages set sequence_number = 2 where content = ?", "첫 답변");
		entityManager.clear();

		List<ChatMessageEntity> messages = chatMessages.findByConversationIdOrderBySequenceNumberDesc(
				conversation.id(), PageRequest.of(0, 12));

		assertThat(messages).extracting(ChatMessageEntity::content)
				.containsExactly("첫 답변", "첫 질문");
		ChatMessageEntity assistant = messages.stream()
				.filter(message -> "assistant".equals(message.role()))
				.findFirst()
				.orElseThrow();
		assertThat(assistant.interactionMeta()).containsEntry("asked_follow_up", true);
	}
}
