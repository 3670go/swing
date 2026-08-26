package com.swinganalyzer.conversation.infrastructure.persistence;

import java.time.Instant;
import java.util.UUID;

import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;

@Entity
@Table(name = "conversations", indexes = {
		@Index(name = "ix_conversations_owner_context_id", columnList = "owner_context_id")
})
public class ConversationEntity {

	@Id
	@GeneratedValue
	private UUID id;

	@Column(name = "owner_context_id", nullable = false)
	private UUID ownerContextId;

	@Column(name = "active_analysis_run_id")
	private UUID activeAnalysisRunId;

	@Column(name = "shot_profile", length = 32)
	private String shotProfile;

	@Column(length = 64)
	private String club;

	@Column(name = "analysis_goal", length = 32)
	private String analysisGoal;

	@CreationTimestamp
	@Column(name = "created_at", nullable = false, updatable = false)
	private Instant createdAt;

	@UpdateTimestamp
	@Column(name = "updated_at", nullable = false)
	private Instant updatedAt;

	protected ConversationEntity() {
	}

	public ConversationEntity(UUID ownerContextId) {
		this.ownerContextId = ownerContextId;
	}

	public void updateContext(String shotProfile, String club, String analysisGoal) {
		this.shotProfile = shotProfile;
		this.club = club;
		this.analysisGoal = analysisGoal;
	}

	public void activateAnalysis(UUID analysisRunId) {
		this.activeAnalysisRunId = analysisRunId;
	}

	public UUID id() {
		return id;
	}

	public UUID ownerContextId() {
		return ownerContextId;
	}
}
