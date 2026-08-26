package com.swinganalyzer.analysis.infrastructure.persistence;

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
@Table(name = "analysis_runs", indexes = {
		@Index(name = "ix_analysis_runs_conversation_id", columnList = "conversation_id"),
		@Index(name = "ix_analysis_runs_status", columnList = "status")
})
public class AnalysisRunEntity {

	@Id
	private UUID id;

	@Column(name = "swing_session_id", nullable = false, unique = true)
	private UUID swingSessionId;

	@Column(name = "conversation_id", nullable = false)
	private UUID conversationId;

	@Column(nullable = false, length = 32)
	private String status;

	@Column(name = "media_kind", nullable = false, length = 16)
	private String mediaKind;

	@Column(length = 64)
	private String model;

	@JdbcTypeCode(SqlTypes.JSON)
	@Column(name = "observation_json", columnDefinition = "jsonb")
	private Map<String, Object> observation;

	@JdbcTypeCode(SqlTypes.JSON)
	@Column(name = "reply_json", columnDefinition = "jsonb")
	private Map<String, Object> reply;

	@Column(name = "error_code", length = 64)
	private String errorCode;

	@CreationTimestamp
	@Column(name = "created_at", nullable = false, updatable = false)
	private Instant createdAt;

	@Column(name = "completed_at")
	private Instant completedAt;

	protected AnalysisRunEntity() {
	}

	public AnalysisRunEntity(UUID swingSessionId, UUID conversationId, String mediaKind, String model) {
		this.id = UUID.randomUUID();
		this.swingSessionId = swingSessionId;
		this.conversationId = conversationId;
		this.status = "running";
		this.mediaKind = mediaKind;
		this.model = model;
	}

	public void complete(String status, Map<String, Object> observation, Map<String, Object> reply) {
		this.status = status;
		this.observation = observation;
		this.reply = reply;
		this.completedAt = Instant.now();
	}

	public void fail(String errorCode) {
		this.status = "failed";
		this.errorCode = errorCode;
		this.completedAt = Instant.now();
	}

	public void delete() {
		this.status = "deleted";
		this.observation = null;
		this.reply = null;
	}

	public UUID id() {
		return id;
	}

	public String status() {
		return status;
	}

	public UUID swingSessionId() {
		return swingSessionId;
	}

	public UUID conversationId() {
		return conversationId;
	}

	public String mediaKind() {
		return mediaKind;
	}

	public Map<String, Object> reply() {
		return reply;
	}

	public Instant createdAt() {
		return createdAt;
	}
}
