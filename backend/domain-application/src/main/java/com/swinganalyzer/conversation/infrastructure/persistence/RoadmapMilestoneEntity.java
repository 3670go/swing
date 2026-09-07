package com.swinganalyzer.conversation.infrastructure.persistence;

import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/**
 * Read mapping for the {@code roadmap_milestones} table (V5). Session 2 reads only.
 */
@Entity
@Table(name = "roadmap_milestones")
public class RoadmapMilestoneEntity {

	@Id
	private UUID id;

	@Column(name = "roadmap_id", nullable = false)
	private UUID roadmapId;

	@Column(nullable = false)
	private int version;

	@Column(name = "sort_order", nullable = false)
	private int sortOrder;

	@Column(nullable = false, length = 200)
	private String title;

	@Column(name = "evidence_level", nullable = false, length = 32)
	private String evidenceLevel;

	@Column(name = "completion_condition", nullable = false, columnDefinition = "text")
	private String completionCondition;

	protected RoadmapMilestoneEntity() {
	}

	/** Promotes the milestone evidence level and bumps the version (Session 3). */
	public void promoteEvidence(String newEvidenceLevel) {
		this.evidenceLevel = newEvidenceLevel;
		this.version = this.version + 1;
	}

	public UUID id() {
		return id;
	}

	public UUID roadmapId() {
		return roadmapId;
	}

	public int version() {
		return version;
	}

	public int sortOrder() {
		return sortOrder;
	}

	public String title() {
		return title;
	}

	public String evidenceLevel() {
		return evidenceLevel;
	}

	public String completionCondition() {
		return completionCondition;
	}
}
