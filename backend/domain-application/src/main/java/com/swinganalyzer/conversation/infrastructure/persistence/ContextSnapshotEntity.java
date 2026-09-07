package com.swinganalyzer.conversation.infrastructure.persistence;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;

import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/**
 * Write mapping for the {@code context_snapshots} table (V5). Records the exact
 * ContextPacket used for a Python call plus the versions and message range it was
 * built from, so a response can be reproduced. The {@code selected_*_refs_json}
 * columns keep their DB defaults and are not mapped in Session 2.
 */
@Entity
@Table(name = "context_snapshots")
public class ContextSnapshotEntity {

	@Id
	private UUID id;

	@Column(name = "request_id", nullable = false)
	private UUID requestId;

	@Column(name = "owner_context_id", nullable = false)
	private UUID ownerContextId;

	@Column(name = "conversation_id")
	private UUID conversationId;

	@Column(name = "analysis_run_id")
	private UUID analysisRunId;

	@Column(name = "topic_id")
	private UUID topicId;

	@Column(name = "topic_version")
	private Integer topicVersion;

	@Column(name = "roadmap_id")
	private UUID roadmapId;

	@Column(name = "roadmap_version")
	private Integer roadmapVersion;

	@Column(name = "open_loop_id")
	private UUID openLoopId;

	@Column(name = "open_loop_version")
	private Integer openLoopVersion;

	@Column(name = "context_snapshot_version", nullable = false)
	private int contextSnapshotVersion;

	@Column(name = "message_sequence_start")
	private Long messageSequenceStart;

	@Column(name = "message_sequence_end")
	private Long messageSequenceEnd;

	@JdbcTypeCode(SqlTypes.JSON)
	@Column(name = "context_packet_json", nullable = false, columnDefinition = "jsonb")
	private Map<String, Object> contextPacketJson;

	@CreationTimestamp
	@Column(name = "created_at", nullable = false, updatable = false)
	private Instant createdAt;

	protected ContextSnapshotEntity() {
	}

	public ContextSnapshotEntity(
			UUID id,
			UUID requestId,
			UUID ownerContextId,
			UUID conversationId,
			UUID analysisRunId,
			UUID topicId,
			Integer topicVersion,
			UUID roadmapId,
			Integer roadmapVersion,
			UUID openLoopId,
			Integer openLoopVersion,
			int contextSnapshotVersion,
			Long messageSequenceStart,
			Long messageSequenceEnd,
			Map<String, Object> contextPacketJson) {
		this.id = id;
		this.requestId = requestId;
		this.ownerContextId = ownerContextId;
		this.conversationId = conversationId;
		this.analysisRunId = analysisRunId;
		this.topicId = topicId;
		this.topicVersion = topicVersion;
		this.roadmapId = roadmapId;
		this.roadmapVersion = roadmapVersion;
		this.openLoopId = openLoopId;
		this.openLoopVersion = openLoopVersion;
		this.contextSnapshotVersion = contextSnapshotVersion;
		this.messageSequenceStart = messageSequenceStart;
		this.messageSequenceEnd = messageSequenceEnd;
		this.contextPacketJson = contextPacketJson;
	}

	public UUID id() {
		return id;
	}

	public UUID requestId() {
		return requestId;
	}

	public UUID topicId() {
		return topicId;
	}

	public Integer topicVersion() {
		return topicVersion;
	}

	public UUID roadmapId() {
		return roadmapId;
	}

	public Integer roadmapVersion() {
		return roadmapVersion;
	}

	public UUID openLoopId() {
		return openLoopId;
	}

	public Integer openLoopVersion() {
		return openLoopVersion;
	}

	public Long messageSequenceStart() {
		return messageSequenceStart;
	}

	public Long messageSequenceEnd() {
		return messageSequenceEnd;
	}

	public Map<String, Object> contextPacketJson() {
		return contextPacketJson;
	}
}
