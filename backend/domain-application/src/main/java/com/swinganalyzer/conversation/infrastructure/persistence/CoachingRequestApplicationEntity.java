package com.swinganalyzer.conversation.infrastructure.persistence;

import java.time.Instant;
import java.util.UUID;

import org.hibernate.annotations.CreationTimestamp;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/**
 * Write mapping for the {@code coaching_request_applications} table (V5). One row
 * per {@code request_id} makes Coaching Turn Plan application idempotent and
 * records whether it applied or was blocked. The DB CHECK enforces that an
 * {@code applied=false} row carries a non-null blocked reason from the allowed set.
 */
@Entity
@Table(name = "coaching_request_applications")
public class CoachingRequestApplicationEntity {

	public static final String DUPLICATE_REQUEST_ID = "DUPLICATE_REQUEST_ID";
	public static final String VERSION_MISMATCH = "VERSION_MISMATCH";
	public static final String ANALYSIS_FAILED = "ANALYSIS_FAILED";
	public static final String CONTRACT_REJECTED = "CONTRACT_REJECTED";

	@Id
	@Column(name = "request_id")
	private UUID requestId;

	@Column(name = "owner_context_id", nullable = false)
	private UUID ownerContextId;

	@Column(name = "conversation_id")
	private UUID conversationId;

	@Column(name = "analysis_run_id")
	private UUID analysisRunId;

	@Column(name = "context_snapshot_id")
	private UUID contextSnapshotId;

	@Column(nullable = false)
	private boolean applied;

	@Column(name = "blocked_reason", length = 64)
	private String blockedReason;

	@CreationTimestamp
	@Column(name = "applied_at", nullable = false, updatable = false)
	private Instant appliedAt;

	protected CoachingRequestApplicationEntity() {
	}

	private CoachingRequestApplicationEntity(
			UUID requestId,
			UUID ownerContextId,
			UUID conversationId,
			UUID analysisRunId,
			UUID contextSnapshotId,
			boolean applied,
			String blockedReason) {
		this.requestId = requestId;
		this.ownerContextId = ownerContextId;
		this.conversationId = conversationId;
		this.analysisRunId = analysisRunId;
		this.contextSnapshotId = contextSnapshotId;
		this.applied = applied;
		this.blockedReason = blockedReason;
	}

	public static CoachingRequestApplicationEntity applied(
			UUID requestId,
			UUID ownerContextId,
			UUID conversationId,
			UUID analysisRunId,
			UUID contextSnapshotId) {
		return new CoachingRequestApplicationEntity(
				requestId, ownerContextId, conversationId, analysisRunId, contextSnapshotId, true, null);
	}

	public static CoachingRequestApplicationEntity blocked(
			UUID requestId,
			UUID ownerContextId,
			UUID conversationId,
			UUID analysisRunId,
			UUID contextSnapshotId,
			String blockedReason) {
		return new CoachingRequestApplicationEntity(
				requestId, ownerContextId, conversationId, analysisRunId, contextSnapshotId, false,
				blockedReason);
	}

	public UUID requestId() {
		return requestId;
	}

	public boolean applied() {
		return applied;
	}

	public String blockedReason() {
		return blockedReason;
	}
}
