package com.swinganalyzer.conversation.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;

import com.swinganalyzer.analysis.application.AiProcessingClient;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.CoachContent;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.ShotContext;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.TextCoachingRequest;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.TextCoachingResponse;
import com.swinganalyzer.conversation.application.ConversationApplicationService.ChatResult;
import com.swinganalyzer.conversation.application.ConversationStore.PreparedConversation;

class ConversationApplicationServiceTests {

	@Test
	void rendersAndPersistsOnlyUserFacingConversationText() {
		ConversationStore store = mock(ConversationStore.class);
		@SuppressWarnings("unchecked")
		ObjectProvider<AiProcessingClient> provider = mock(ObjectProvider.class);
		AiProcessingClient client = mock(AiProcessingClient.class);
		ConversationRenderer renderer = new ConversationRenderer();
		ConversationApplicationService service = new ConversationApplicationService(
				store, provider, renderer);
		UUID conversationId = UUID.randomUUID();
		when(provider.getIfAvailable()).thenReturn(client);
		when(store.prepareTextTurn(any(), any(), any(), any()))
				.thenReturn(new PreparedConversation(conversationId, List.of(), false));
		when(client.coachText(any(TextCoachingRequest.class))).thenAnswer(invocation -> {
			TextCoachingRequest request = invocation.getArgument(0);
			return new TextCoachingResponse(request.requestId(), coachContent());
		});

		ChatResult result = service.chat(
				"anonymous-session-0001",
				null,
				"자꾸 당겨 치는 느낌이야",
				new ShotContext("full_swing", "7번 아이언", "face_on", "right",
						"posture_correction", null, null, null));

		assertThat(result.reply())
				.contains("가슴이 먼저 열리는지 확인해보세요")
				.doesNotContain("evidence_mode", "observation_indexes");
		verify(store).saveAssistant(eq(conversationId), eq(result.reply()), any());
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
}
