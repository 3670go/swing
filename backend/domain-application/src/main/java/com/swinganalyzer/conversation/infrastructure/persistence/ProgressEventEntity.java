package com.swinganalyzer.conversation.infrastructure.persistence;

import java.time.Instant;
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/**
 * Read mapping for the {@code progress_events} table (V5). Session 2 reads only.
 */
@Entity
@Table(name = "progress_events")
public class ProgressEventEntity {

	@Id
	private UUID id;

	@Column(name = "owner_context_id", nullable = false)
	private UUID ownerContextId;

	@Column(name = "topic_id", nullable = false)
	private UUID topicId;

	@Column(name = "milestone_id")
	private UUID milestoneId;

	@Column(nullable = false)
	private int version;

	@Column(name = "progress_level", nullable = false, length = 32)
	private String progressLevel;

	@Column(name = "user_signal", nullable = false, columnDefinition = "text")
	private String userSignal;

	@Column(nullable = false)
	private boolean recognized;

	@Column(name = "created_at", nullable = false, updatable = false, insertable = false)
	private Instant createdAt;

	protected ProgressEventEntity() {
	}

	/**
	 * Creates a new (not yet recognized) progress event (Session 3).
	 * {@code created_at} and {@code evidence_references_json} are left to the DB.
	 */
	public ProgressEventEntity(
			UUID ownerContextId,
			UUID topicId,
			UUID milestoneId,
			String progressLevel,
			String userSignal) {
		this.id = UUID.randomUUID();
		this.ownerContextId = ownerContextId;
		this.topicId = topicId;
		this.milestoneId = milestoneId;
		this.version = 1;
		this.progressLevel = progressLevel;
		this.userSignal = userSignal;
		this.recognized = false;
	}

	public void markRecognized() {
		this.recognized = true;
	}

	public UUID id() {
		return id;
	}

	public UUID topicId() {
		return topicId;
	}

	public UUID milestoneId() {
		return milestoneId;
	}

	public String progressLevel() {
		return progressLevel;
	}

	public String userSignal() {
		return userSignal;
	}

	public boolean recognized() {
		return recognized;
	}

	public Instant createdAt() {
		return createdAt;
	}
}
