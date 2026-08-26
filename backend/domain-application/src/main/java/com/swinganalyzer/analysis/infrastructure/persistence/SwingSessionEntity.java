package com.swinganalyzer.analysis.infrastructure.persistence;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;

import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;

@Entity
@Table(name = "swing_sessions", indexes = {
		@Index(name = "ix_swing_sessions_owner_context_id", columnList = "owner_context_id"),
		@Index(name = "ix_swing_sessions_conversation_id", columnList = "conversation_id")
})
public class SwingSessionEntity {

	@Id
	@GeneratedValue
	private UUID id;

	@Column(name = "owner_context_id", nullable = false)
	private UUID ownerContextId;

	@Column(name = "conversation_id", nullable = false)
	private UUID conversationId;

	@Column(name = "shot_profile", nullable = false, length = 32)
	private String shotProfile;

	@Column(nullable = false, length = 64)
	private String club;

	@Column(name = "camera_view", nullable = false, length = 32)
	private String cameraView;

	@Column(nullable = false, length = 16)
	private String handedness;

	@Column(name = "user_question", columnDefinition = "text")
	private String userQuestion;

	@Column(name = "user_feel", columnDefinition = "text")
	private String userFeel;

	@JdbcTypeCode(SqlTypes.JSON)
	@Column(name = "shot_result_json", columnDefinition = "jsonb")
	private Map<String, Object> shotResult;

	@Column(name = "comparison_session_id")
	private UUID comparisonSessionId;

	@CreationTimestamp
	@Column(name = "created_at", nullable = false, updatable = false)
	private Instant createdAt;

	protected SwingSessionEntity() {
	}

	public SwingSessionEntity(UUID ownerContextId, UUID conversationId, String shotProfile, String club,
			String cameraView, String handedness, String userQuestion, String userFeel,
			Map<String, Object> shotResult, UUID comparisonSessionId) {
		this.ownerContextId = ownerContextId;
		this.conversationId = conversationId;
		this.shotProfile = shotProfile;
		this.club = club;
		this.cameraView = cameraView;
		this.handedness = handedness;
		this.userQuestion = userQuestion;
		this.userFeel = userFeel;
		this.shotResult = shotResult;
		this.comparisonSessionId = comparisonSessionId;
	}

	public UUID id() {
		return id;
	}

	public UUID ownerContextId() {
		return ownerContextId;
	}
}
