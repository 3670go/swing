package com.swinganalyzer.conversation.infrastructure.persistence;

import java.time.Instant;
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/**
 * Read mapping for the {@code recognition_events} table (V5). Session 2 reads only.
 */
@Entity
@Table(name = "recognition_events")
public class RecognitionEventEntity {

	@Id
	private UUID id;

	@Column(name = "owner_context_id", nullable = false)
	private UUID ownerContextId;

	@Column(name = "topic_id", nullable = false)
	private UUID topicId;

	@Column(name = "progress_event_id", nullable = false)
	private UUID progressEventId;

	@Column(name = "roadmap_id")
	private UUID roadmapId;

	@Column(name = "milestone_id")
	private UUID milestoneId;

	@Column(name = "milestone_version")
	private Integer milestoneVersion;

	@Column(nullable = false, length = 32)
	private String intensity;

	@Column(nullable = false, length = 200)
	private String target;

	@Column(name = "recognition_content", nullable = false, columnDefinition = "text")
	private String recognitionContent;

	@Column(name = "exposed_at", nullable = false, updatable = false, insertable = false)
	private Instant exposedAt;

	protected RecognitionEventEntity() {
	}

	/**
	 * Records a recognition exposed to the user for one progress event (Session 3).
	 * {@code exposed_at} and {@code evidence_references_json} are left to the DB.
	 */
	public RecognitionEventEntity(
			UUID ownerContextId,
			UUID topicId,
			UUID progressEventId,
			UUID roadmapId,
			UUID milestoneId,
			Integer milestoneVersion,
			String intensity,
			String target,
			String recognitionContent) {
		this.id = UUID.randomUUID();
		this.ownerContextId = ownerContextId;
		this.topicId = topicId;
		this.progressEventId = progressEventId;
		this.roadmapId = roadmapId;
		this.milestoneId = milestoneId;
		this.milestoneVersion = milestoneVersion;
		this.intensity = intensity;
		this.target = target;
		this.recognitionContent = recognitionContent;
	}

	public UUID id() {
		return id;
	}

	public UUID topicId() {
		return topicId;
	}

	public UUID roadmapId() {
		return roadmapId;
	}

	public Integer milestoneVersion() {
		return milestoneVersion;
	}

	public Instant exposedAt() {
		return exposedAt;
	}
}
