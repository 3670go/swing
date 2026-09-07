package com.swinganalyzer.conversation.infrastructure.persistence;

import java.time.Instant;
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/**
 * Read mapping for the {@code open_loops} table (V5). Session 2 reads only.
 */
@Entity
@Table(name = "open_loops")
public class OpenLoopEntity {

	@Id
	private UUID id;

	@Column(name = "owner_context_id", nullable = false)
	private UUID ownerContextId;

	@Column(name = "topic_id", nullable = false)
	private UUID topicId;

	@Column(nullable = false)
	private int version;

	@Column(nullable = false, length = 32)
	private String state;

	@Column(name = "carry_forward_feel", columnDefinition = "text")
	private String carryForwardFeel;

	@Column(name = "next_single_change", nullable = false, columnDefinition = "text")
	private String nextSingleChange;

	@Column(name = "next_verification", nullable = false, columnDefinition = "text")
	private String nextVerification;

	@Column(name = "completion_condition", nullable = false, columnDefinition = "text")
	private String completionCondition;

	@Column(name = "predicted_result", columnDefinition = "text")
	private String predictedResult;

	@Column(length = 300)
	private String question;

	@Column(name = "created_at", nullable = false, updatable = false, insertable = false)
	private Instant createdAt;

	protected OpenLoopEntity() {
	}

	/**
	 * Creates a new PENDING open loop for a topic (Session 3). {@code created_at},
	 * {@code next_upload_expected} and other defaulted columns are left to the DB.
	 */
	public OpenLoopEntity(
			UUID ownerContextId,
			UUID topicId,
			String carryForwardFeel,
			String nextSingleChange,
			String nextVerification,
			String completionCondition,
			String predictedResult,
			String question) {
		this.id = UUID.randomUUID();
		this.ownerContextId = ownerContextId;
		this.topicId = topicId;
		this.version = 1;
		this.state = "PENDING";
		this.carryForwardFeel = carryForwardFeel;
		this.nextSingleChange = nextSingleChange;
		this.nextVerification = nextVerification;
		this.completionCondition = completionCondition;
		this.predictedResult = predictedResult;
		this.question = question;
	}

	/** Closes this PENDING loop because a newer verification plan replaced it. */
	public void markReplaced() {
		this.state = "REPLACED";
	}

	public UUID id() {
		return id;
	}

	public UUID topicId() {
		return topicId;
	}

	public int version() {
		return version;
	}

	public String state() {
		return state;
	}

	public String carryForwardFeel() {
		return carryForwardFeel;
	}

	public String nextSingleChange() {
		return nextSingleChange;
	}

	public String nextVerification() {
		return nextVerification;
	}

	public String predictedResult() {
		return predictedResult;
	}

	public Instant createdAt() {
		return createdAt;
	}
}
