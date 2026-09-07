package com.swinganalyzer.conversation.application;

import java.util.Map;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.swinganalyzer.analysis.application.model.AiProcessingContract.ContextPacket;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext;
import com.swinganalyzer.conversation.infrastructure.persistence.ContextSnapshotEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.ContextSnapshotJpaRepository;

import tools.jackson.databind.ObjectMapper;

/**
 * Persists the {@link ContextPacket} actually sent to the AI Processing Unit as a
 * {@code context_snapshots} row, together with the versions and message range it
 * was built from. The stored {@code context_packet_json} is the same packet that
 * was sent, so a response can be reproduced.
 *
 * <p>Session 2 flow decision: the snapshot is written only after a successful
 * Python response, in the same success path as the assistant message. On a Python
 * failure no snapshot is written and no coaching state changes, matching the
 * boundary contract (a failed call preserves existing coaching state).
 */
@Service
public class ContextSnapshotStore {

	private final ContextSnapshotJpaRepository snapshots;
	private final ObjectMapper objectMapper;

	public ContextSnapshotStore(
			ContextSnapshotJpaRepository snapshots, ObjectMapper objectMapper) {
		this.snapshots = snapshots;
		this.objectMapper = objectMapper;
	}

	@Transactional
	public void save(
			UUID snapshotId,
			UUID requestId,
			UUID ownerContextId,
			UUID conversationId,
			UUID analysisRunId,
			ContextSelection selection,
			ContextPacket packet) {
		RetrievedCoachingContext coaching = selection.coachingContext();
		UUID topicId = coaching.activeTopic() == null ? null : coaching.activeTopic().topicId();
		Integer topicVersion = coaching.activeTopic() == null ? null : coaching.activeTopic().version();
		UUID roadmapId = coaching.roadmap() == null ? null : coaching.roadmap().roadmapId();
		Integer roadmapVersion = coaching.roadmap() == null ? null : coaching.roadmap().version();
		UUID openLoopId = coaching.pendingOpenLoop() == null ? null : coaching.pendingOpenLoop().openLoopId();
		Integer openLoopVersion = coaching.pendingOpenLoop() == null
				? null : coaching.pendingOpenLoop().version();

		@SuppressWarnings("unchecked")
		Map<String, Object> packetJson = objectMapper.convertValue(packet, Map.class);

		snapshots.save(new ContextSnapshotEntity(
				snapshotId,
				requestId,
				ownerContextId,
				conversationId,
				analysisRunId,
				topicId,
				topicVersion,
				roadmapId,
				roadmapVersion,
				openLoopId,
				openLoopVersion,
				packet.contextSnapshotVersion(),
				selection.messageSequenceStart(),
				selection.messageSequenceEnd(),
				packetJson));
	}
}
