package com.swinganalyzer.conversation.infrastructure.persistence;

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

	@Column(name = "next_completion_condition", columnDefinition = "text")
	private String nextCompletionCondition;

	protected RoadmapEntity() {
	}

	public UUID id() {
		return id;
	}

	public UUID topicId() {
		return topicId;
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

	public String nextCompletionCondition() {
		return nextCompletionCondition;
	}
}
