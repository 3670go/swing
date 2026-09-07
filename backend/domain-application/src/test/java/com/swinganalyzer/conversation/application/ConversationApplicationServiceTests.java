package com.swinganalyzer.conversation.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.ObjectProvider;

import com.swinganalyzer.analysis.application.AiProcessingClient;
import com.swinganalyzer.analysis.application.AiProcessingClientException;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.CoachContent;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.CoachingTurnPlan;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.ContextPacket;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.InternalTextCoachingRequest;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.InternalTextCoachingResponse;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.ShotContext;
import com.swinganalyzer.conversation.application.ConversationApplicationService.ChatResult;
import com.swinganalyzer.conversation.application.ConversationStore.PreparedConversation;

class ConversationApplicationServiceTests {

	private static final ShotContext SHOT_CONTEXT = new ShotContext(
			"full_swing", "7번 아이언", "face_on", "right", "posture_correction", null, null, null);

	@Test
	void rendersPersistsAndSnapshotsOnSuccess() {
		Fixture fixture = new Fixture();
		UUID conversationId = UUID.randomUUID();
		UUID ownerId = UUID.randomUUID();
		when(fixture.provider.getIfAvailable()).thenReturn(fixture.client);
		when(fixture.store.prepareTextTurn(any(), any(), any(), any()))
				.thenReturn(new PreparedConversation(conversationId, ownerId));
		when(fixture.retrieval.retrieve(eq(ownerId), eq(conversationId), any(), any()))
				.thenReturn(ContextSelection.empty());
		when(fixture.client.coachText(any(InternalTextCoachingRequest.class))).thenAnswer(invocation -> {
			InternalTextCoachingRequest request = invocation.getArgument(0);
			return new InternalTextCoachingResponse(request.requestId(), turnPlan());
		});

		ChatResult result = fixture.service.chat(
				"anonymous-session-0001", null, "자꾸 당겨 치는 느낌이야", SHOT_CONTEXT);

		assertThat(result.reply())
				.contains("가슴이 먼저 열리는지 확인해보세요")
				.doesNotContain("evidence_mode", "observation_indexes");
		verify(fixture.store).saveAssistant(eq(conversationId), eq(result.reply()), any());

		ArgumentCaptor<InternalTextCoachingRequest> sent =
				ArgumentCaptor.forClass(InternalTextCoachingRequest.class);
		verify(fixture.client).coachText(sent.capture());
		ArgumentCaptor<ContextPacket> snapshotPacket = ArgumentCaptor.forClass(ContextPacket.class);
		verify(fixture.snapshotStore).save(
				any(), eq(sent.getValue().requestId()), eq(ownerId), eq(conversationId),
				eq(null), any(), snapshotPacket.capture());
		// The snapshotted packet must be the exact packet sent to Python.
		assertThat(snapshotPacket.getValue()).isEqualTo(sent.getValue().contextPacket());
	}

	@Test
	void doesNotSnapshotOrChangeStateWhenPythonFails() {
		Fixture fixture = new Fixture();
		UUID conversationId = UUID.randomUUID();
		UUID ownerId = UUID.randomUUID();
		when(fixture.provider.getIfAvailable()).thenReturn(fixture.client);
		when(fixture.store.prepareTextTurn(any(), any(), any(), any()))
				.thenReturn(new PreparedConversation(conversationId, ownerId));
		when(fixture.retrieval.retrieve(eq(ownerId), eq(conversationId), any(), any()))
				.thenReturn(ContextSelection.empty());
		when(fixture.client.coachText(any(InternalTextCoachingRequest.class)))
				.thenThrow(new AiProcessingClientException(
						"MODEL_TIMEOUT", "timed out", false, 504, UUID.randomUUID(), null, null));

		try {
			fixture.service.chat("anonymous-session-0001", null, "당겨 친다", SHOT_CONTEXT);
		} catch (RuntimeException expected) {
			// mapped to a PublicApiException; state invariance is what we assert below
		}

		verifyNoInteractions(fixture.snapshotStore);
		verifyNoInteractions(fixture.planApplication);
		verify(fixture.store, org.mockito.Mockito.never()).saveAssistant(any(), any(), any());
	}

	private static CoachingTurnPlan turnPlan() {
		return new CoachingTurnPlan(coachContent(), null, null, List.of(), null, null, null);
	}

	private static CoachContent coachContent() {
		return new CoachContent(
				"text_only",
				"가슴이 먼저 열리는지 확인해보세요.",
				List.of("전환 초반 회전", "팔 하강 공간 감소"),
				"영상이 없어 실제 동작은 확정할 수 없습니다.",
				List.of("실제 클럽 패스"),
				List.of(),
				null,
				"다운스윙 시작을 한 박자만 늦춰보세요.",
				"후방 영상에서 손이 내려올 공간을 확인하세요.",
				null,
				null,
				null);
	}

	private static final class Fixture {
		final ConversationStore store = mock(ConversationStore.class);
		@SuppressWarnings("unchecked")
		final ObjectProvider<AiProcessingClient> provider = mock(ObjectProvider.class);
		final AiProcessingClient client = mock(AiProcessingClient.class);
		final ConversationRenderer renderer = new ConversationRenderer();
		final ContextRetrievalService retrieval = mock(ContextRetrievalService.class);
		final ContextPacketAssembler assembler = new ContextPacketAssembler();
		final ContextSnapshotStore snapshotStore = mock(ContextSnapshotStore.class);
		final CoachingPlanApplicationService planApplication = mock(CoachingPlanApplicationService.class);
		final ConversationApplicationService service = new ConversationApplicationService(
				store, provider, renderer, retrieval, assembler, snapshotStore, planApplication);
	}
}
