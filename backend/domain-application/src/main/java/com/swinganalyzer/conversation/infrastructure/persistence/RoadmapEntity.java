package com.swinganalyzer.conversation.infrastructure.persistence;

import java.time.Instant;
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/**
 * Read mapping for the {@code roadmaps} table (V5). Session 2 reads only.
 */
@Entity
@Table(name = "roadmaps")
public class RoadmapEntity {

	@Id
	private UUID id;

	@Column(name = "owner_context_id", nullable = false)
	private UUID ownerContextId;

	@Column(name = "topic_id")
	private UUID topicId;

	@Column(name = "current_milestone_id")
	private UUID currentMilestoneId;

	@Column(nullable = false)
	private int version;

	@Column(name = "is_active", nullable = false)
	private boolean active;

	@Column(name = "target_swing", nullable = false, columnDefinition = "text")
	private String targetSwing;

	@Column(name = "starting_state", columnDefinition = "text")
	private String startingState;

	@Column(name = "next_completion_condition", columnDefinition = "text")
	private String nextCompletionCondition;

	@Column(name = "archived_at")
	private Instant archivedAt;

	protected RoadmapEntity() {
	}

	public RoadmapEntity(
			UUID ownerContextId,
			UUID topicId,
			String targetSwing,
			String startingState,
			String nextCompletionCondition) {
		this.id = UUID.randomUUID();
		this.ownerContextId = ownerContextId;
		this.topicId = topicId;
		this.version = 1;
		this.active = true;
		this.targetSwing = targetSwing;
		this.startingState = startingState;
		this.nextCompletionCondition = nextCompletionCondition;
	}

	public void selectCurrentMilestone(UUID milestoneId) {
		this.currentMilestoneId = milestoneId;
	}

	public void archive() {
		this.active = false;
		this.archivedAt = Instant.now();
		this.version = this.version + 1;
	}

	public UUID id() {
		return id;
	}

	public UUID topicId() {
		return topicId;
	}

	public UUID ownerContextId() {
		return ownerContextId;
	}

	public UUID currentMilestoneId() {
		return currentMilestoneId;
	}

	public int version() {
		return version;
	}

	public boolean active() {
		return active;
	}

	public String targetSwing() {
		return targetSwing;
	}

	public String startingState() {
		return startingState;
	}

	public String nextCompletionCondition() {
		return nextCompletionCondition;
	}
}
