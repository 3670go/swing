package com.swinganalyzer.conversation.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import com.swinganalyzer.analysis.infrastructure.persistence.AnalysisRunEntity;
import com.swinganalyzer.analysis.infrastructure.persistence.AnalysisRunJpaRepository;
import com.swinganalyzer.analysis.infrastructure.persistence.SwingSessionEntity;
import com.swinganalyzer.analysis.infrastructure.persistence.SwingSessionJpaRepository;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.ShotContext;
import com.swinganalyzer.conversation.infrastructure.persistence.CoachingTopicEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.CoachingTopicJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.ChatMessageEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.ChatMessageJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.ConversationEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.ConversationJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.OwnerContextEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.OwnerContextJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.RoadmapJpaRepository;

@SpringBootTest(
		classes = { com.swinganalyzer.SwingAnalyzerApplication.class, MemberJourneyIntegrationTests.JwtTestConfiguration.class },
		properties = {
				"spring.datasource.url=jdbc:h2:mem:member-journey;MODE=PostgreSQL;DB_CLOSE_DELAY=-1",
				"spring.datasource.username=sa",
				"spring.datasource.password=",
				"spring.jpa.hibernate.ddl-auto=create-drop",
				"spring.flyway.enabled=false"
		})
@AutoConfigureMockMvc
@Transactional
class MemberJourneyIntegrationTests {

	private static final String TOKEN = "member-journey-token";
	private static final String SUBJECT = "member-subject-journey";
	private static final String SESSION_ID = "anonymous-session-member-journey-0001";

	@Autowired
	private MockMvc mvc;

	@Autowired
	private OwnerContextJpaRepository owners;

	@Autowired
	private ConversationJpaRepository conversations;

	@Autowired
	private ChatMessageJpaRepository chatMessages;

	@Autowired
	private SwingSessionJpaRepository swingSessions;

	@Autowired
	private AnalysisRunJpaRepository analysisRuns;

	@Autowired
	private CoachingTopicJpaRepository topics;

	@Autowired
	private RoadmapJpaRepository roadmaps;

	@Autowired
	private ContextRetrievalService contextRetrieval;

	@Test
	void claimsGuestThenRestoresProfileAndRoadmapForSameMember() throws Exception {
		OwnerContextEntity guest = owners.saveAndFlush(
				new OwnerContextEntity(ConversationStore.hashAnonymousSession(SESSION_ID)));
		ConversationEntity conversation = conversations.saveAndFlush(new ConversationEntity(guest.id()));
		chatMessages.saveAndFlush(new ChatMessageEntity(
				conversation.id(), null, "user", "가입 전에 당겨 치는 문제를 질문했어", null));
		chatMessages.saveAndFlush(new ChatMessageEntity(
				conversation.id(), null, "assistant", "가슴 회전 순서를 먼저 확인해보세요.", null));
		SwingSessionEntity swing = swingSessions.saveAndFlush(new SwingSessionEntity(
				guest.id(), conversation.id(), "full_swing", "7번 아이언", "face_on", "right",
				"왜 당겨 치나요?", null, Map.of(), null));
		AnalysisRunEntity run = new AnalysisRunEntity(
				swing.id(), conversation.id(), "video", "journey-test-model");
		run.complete(
				"succeeded",
				Map.of(),
				Map.of("content", Map.of(
						"single_change", "가슴 회전을 한 박자 늦춘다",
						"verification", "후방 영상에서 손이 내려오는 공간을 확인한다")));
		analysisRuns.saveAndFlush(run);
		CoachingTopicEntity topic = topics.saveAndFlush(new CoachingTopicEntity(
				guest.id(), conversation.id(), "다운스윙 때 당겨 침", "full_swing",
				"7번 아이언", null, null));

		mvc.perform(post("/v1/me/claim")
				.header("Authorization", "Bearer " + TOKEN)
				.contentType(MediaType.APPLICATION_JSON)
				.content("{\"anonymous_session_id\":\"" + SESSION_ID + "\"}"))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.owner_context_id").value(guest.id().toString()));

		assertThat(owners.findByExternalProviderAndExternalSubject("supabase", SUBJECT))
				.map(OwnerContextEntity::id)
				.contains(guest.id());

		mvc.perform(put("/v1/me/profile")
				.header("Authorization", "Bearer " + TOKEN)
				.contentType(MediaType.APPLICATION_JSON)
				.content("""
						{
						  "display_name": "발표 골퍼",
						  "default_handedness": "right",
						  "current_swing_style": "페이드",
						  "target_swing_style": "스트레이트",
						  "body_traits": [{"body_region": "상체", "statement": "회전이 빠름"}],
						  "injuries": []
						}
						"""))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.display_name").value("발표 골퍼"))
				.andExpect(jsonPath("$.target_swing_style").value("스트레이트"));

		mvc.perform(post("/v1/me/roadmaps")
				.header("Authorization", "Bearer " + TOKEN)
				.contentType(MediaType.APPLICATION_JSON)
				.content("""
						{"analysis_run_id":"%s","target_swing":"일관된 스트레이트 구질"}
						""".formatted(run.id())))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.target_swing").value("일관된 스트레이트 구질"))
				.andExpect(jsonPath("$.current_milestone.evidence_level").value("NOT_STARTED"));

		assertThat(roadmaps.findFirstByTopicIdAndActiveTrue(topic.id())).isPresent();
		ContextSelection restoredContext = contextRetrieval.retrieve(
				guest.id(),
				conversation.id(),
				new ShotContext(
						"full_swing", "7번 아이언", "face_on", "right",
						"posture_correction", null, null, null),
				"다음 연습은 어떻게 할까?");
		assertThat(restoredContext.coachingContext().facts())
				.extracting(com.swinganalyzer.conversation.domain.RetrievedCoachingContext.Fact::statement)
				.contains("페이드", "스트레이트", "회전이 빠름");
		assertThat(restoredContext.coachingContext().roadmap().targetSwing())
				.isEqualTo("일관된 스트레이트 구질");

		mvc.perform(get("/v1/me/profile")
				.header("Authorization", "Bearer " + TOKEN))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.display_name").value("발표 골퍼"));

		mvc.perform(get("/v1/me/roadmaps/active")
				.header("Authorization", "Bearer " + TOKEN))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.roadmap.target_swing").value("일관된 스트레이트 구질"))
				.andExpect(jsonPath("$.roadmap.current_milestone.title")
						.value("가슴 회전을 한 박자 늦춘다"));

		mvc.perform(get("/v1/history")
				.header("Authorization", "Bearer " + TOKEN)
				.param("anonymous_session_id", SESSION_ID))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.items[0].analysis_run_id").value(run.id().toString()));

		mvc.perform(get("/v1/conversations/latest")
				.header("Authorization", "Bearer " + TOKEN)
				.param("anonymous_session_id", SESSION_ID))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.conversation_id").value(conversation.id().toString()))
				.andExpect(jsonPath("$.messages.length()").value(2));
	}

	@TestConfiguration
	static class JwtTestConfiguration {

		@Bean
		@Primary
		JwtDecoder journeyJwtDecoder() {
			return token -> Jwt.withTokenValue(token)
					.header("alg", "test")
					.subject(SUBJECT)
					.audience(List.of("authenticated"))
					.issuedAt(Instant.now().minusSeconds(60))
					.expiresAt(Instant.now().plusSeconds(3600))
					.build();
		}
	}
}
