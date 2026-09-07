package com.swinganalyzer.conversation.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import com.swinganalyzer.analysis.application.model.AiProcessingContract.ContextPacket;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.ShotContext;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.ActiveTopic;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.CoachingScope;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.OpenLoop;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.Recognition;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.Roadmap;
import com.swinganalyzer.conversation.infrastructure.persistence.ContextSnapshotEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.ContextSnapshotJpaRepository;

import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.json.JsonMapper;

class ContextSnapshotStoreTests {

	private static final ShotContext SHOT = new ShotContext(
			"full_swing", "7-iron", "down_the_line", "right", "posture_correction", null, null, null);

	private final ContextSnapshotJpaRepository snapshots = mock(ContextSnapshotJpaRepository.class);
	private final JsonMapper objectMapper = JsonMapper.builder()
			.propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
			.build();
	private final ContextSnapshotStore store = new ContextSnapshotStore(snapshots, objectMapper);
	private final ContextPacketAssembler assembler = new ContextPacketAssembler();

	@Test
	void storesTheExactPacketWithSelectedVersionsAndRange() {
		UUID snapshotId = UUID.randomUUID();
		UUID requestId = UUID.randomUUID();
		UUID owner = UUID.randomUUID();
		UUID conversation = UUID.randomUUID();
		UUID topicId = UUID.randomUUID();
		UUID roadmapId = UUID.randomUUID();
		UUID openLoopId = UUID.randomUUID();

		CoachingScope scope = new CoachingScope("full_swing", "7-iron", "iron", null);
		RetrievedCoachingContext coaching = new RetrievedCoachingContext(
				new ActiveTopic(topicId, 2, "당겨 친다", null, scope, null, null, null),
				new Roadmap(roadmapId, 3, "반복 가능한 스윙", null, List.of(), null),
				List.of(),
				new OpenLoop(openLoopId, 1, null, "감각 유지", "확인", null),
				Recognition.empty());
		ContextSelection selection = new ContextSelection(coaching, List.of(), 5L, 9L);
		ContextPacket packet = assembler.assemble(snapshotId, "질문", SHOT, false, selection);

		when(snapshots.save(any())).thenAnswer(invocation -> invocation.getArgument(0));

		store.save(snapshotId, requestId, owner, conversation, null, selection, packet);

		ArgumentCaptor<ContextSnapshotEntity> saved = ArgumentCaptor.forClass(ContextSnapshotEntity.class);
		verify(snapshots).save(saved.capture());
		ContextSnapshotEntity entity = saved.getValue();

		assertThat(entity.id()).isEqualTo(snapshotId);
		assertThat(entity.requestId()).isEqualTo(requestId);
		assertThat(entity.topicId()).isEqualTo(topicId);
		assertThat(entity.topicVersion()).isEqualTo(2);
		assertThat(entity.roadmapId()).isEqualTo(roadmapId);
		assertThat(entity.roadmapVersion()).isEqualTo(3);
		assertThat(entity.openLoopId()).isEqualTo(openLoopId);
		assertThat(entity.openLoopVersion()).isEqualTo(1);
		assertThat(entity.messageSequenceStart()).isEqualTo(5L);
		assertThat(entity.messageSequenceEnd()).isEqualTo(9L);

		Map<String, Object> expected = objectMapper.convertValue(packet, Map.class);
		assertThat(entity.contextPacketJson()).isEqualTo(expected);
		assertThat(entity.contextPacketJson().get("context_snapshot_id"))
				.isEqualTo(snapshotId.toString());
	}
}
