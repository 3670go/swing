package com.swinganalyzer.conversation.infrastructure.persistence;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;

import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;

@Entity
@Table(name = "chat_messages", indexes = {
		@Index(name = "ix_chat_messages_conversation_id", columnList = "conversation_id"),
		@Index(name = "ix_chat_messages_created_at", columnList = "created_at")
})
public class ChatMessageEntity {

	@Id
	private UUID id;

	@Column(name = "conversation_id", nullable = false)
	private UUID conversationId;

	@Column(name = "analysis_run_id")
	private UUID analysisRunId;

	@Column(nullable = false, length = 16)
	private String role;

	@Column(nullable = false, columnDefinition = "text")
	private String content;

	@JdbcTypeCode(SqlTypes.JSON)
	@Column(name = "interaction_meta_json", columnDefinition = "jsonb")
	private Map<String, Object> interactionMeta;

	@CreationTimestamp
	@Column(name = "created_at", nullable = false, updatable = false)
	private Instant createdAt;

	@Column(name = "sequence_number", insertable = false, updatable = false)
	private Long sequenceNumber;

	protected ChatMessageEntity() {
	}

	public ChatMessageEntity(UUID conversationId, UUID analysisRunId, String role, String content,
			Map<String, Object> interactionMeta) {
		this.id = UUID.randomUUID();
		this.conversationId = conversationId;
		this.analysisRunId = analysisRunId;
		this.role = role;
		this.content = content;
		this.interactionMeta = interactionMeta;
	}

	public UUID id() {
		return id;
	}

	public String role() {
		return role;
	}

	public String content() {
		return content;
	}

	public Map<String, Object> interactionMeta() {
		return interactionMeta;
	}

	public Long sequenceNumber() {
		return sequenceNumber;
	}
}
