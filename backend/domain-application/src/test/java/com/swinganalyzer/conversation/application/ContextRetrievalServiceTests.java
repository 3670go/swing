package com.swinganalyzer.conversation.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.data.domain.PageRequest;

import com.swinganalyzer.analysis.application.model.AiProcessingContract.ShotContext;
import com.swinganalyzer.conversation.infrastructure.persistence.ChatMessageEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.ChatMessageJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.CoachingTopicEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.CoachingTopicJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.OpenLoopEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.OpenLoopJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.ProgressEventEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.ProgressEventJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.RecognitionEventJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.RoadmapEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.RoadmapJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.RoadmapMilestoneEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.RoadmapMilestoneJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.UserContextFactEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.UserContextFactJpaRepository;

class ContextRetrievalServiceTests {

	private static final ShotContext IRON_REQUEST = new ShotContext(
			"full_swing", "7-iron", "down_the_line", "right", "posture_correction", null, null, null);

	private final ChatMessageJpaRepository messages = mock(ChatMessageJpaRepository.class);
	private final CoachingTopicJpaRepository topics = mock(CoachingTopicJpaRepository.class);
	private final RoadmapJpaRepository roadmaps = mock(RoadmapJpaRepository.class);
	private final RoadmapMilestoneJpaRepository milestones = mock(RoadmapMilestoneJpaRepository.class);
	private final UserContextFactJpaRepository facts = mock(UserContextFactJpaRepository.class);
	private final ProgressEventJpaRepository progressEvents = mock(ProgressEventJpaRepository.class);
	private final RecognitionEventJpaRepository recognitionEvents = mock(RecognitionEventJpaRepository.class);
	private final OpenLoopJpaRepository openLoops = mock(OpenLoopJpaRepository.class);

	private final ContextRetrievalService service = new ContextRetrievalService(
			messages, topics, roadmaps, milestones, facts, progressEvents, recognitionEvents, openLoops);

	@Test
	void includesActiveTopicRoadmapOpenLoopAndProgressWhenScopeMatches() {
		UUID owner = UUID.randomUUID();
		UUID conversation = UUID.randomUUID();
		UUID topicId = UUID.randomUUID();
		UUID roadmapId = UUID.randomUUID();
		UUID milestoneId = UUID.randomUUID();

		CoachingTopicEntity topic = topic(topicId, "full_swing", "7-iron", "iron", null);
		RoadmapEntity roadmap = roadmap(roadmapId, milestoneId);
		RoadmapMilestoneEntity milestone = milestone(milestoneId);
		OpenLoopEntity openLoop = openLoop();
		ProgressEventEntity progress = progressEvent(topicId);
		when(topics.findFirstByOwnerContextIdAndStatus(owner, "ACTIVE"))
				.thenReturn(Optional.of(topic));
		when(roadmaps.findFirstByTopicIdAndActiveTrue(topicId))
				.thenReturn(Optional.of(roadmap));
		when(milestones.findById(milestoneId)).thenReturn(Optional.of(milestone));
		when(openLoops.findFirstByTopicIdAndStateOrderByCreatedAtDesc(topicId, "PENDING"))
				.thenReturn(Optional.of(openLoop));
		when(progressEvents.findByOwnerContextIdAndTopicIdAndRecognizedFalseOrderByCreatedAtAsc(
				eq(owner), eq(topicId), any())).thenReturn(List.of(progress));

		ContextSelection selection = service.retrieve(owner, conversation, IRON_REQUEST, "질문");

		assertThat(selection.coachingContext().activeTopic()).isNotNull();
		assertThat(selection.coachingContext().activeTopic().topicId()).isEqualTo(topicId);
		assertThat(selection.coachingContext().roadmap()).isNotNull();
		assertThat(selection.coachingContext().roadmap().currentMilestone()).isNotNull();
		assertThat(selection.coachingContext().pendingOpenLoop()).isNotNull();
		assertThat(selection.coachingContext().recognition().unrecognizedProgressEvents()).hasSize(1);
		verify(milestones).findByRoadmapIdAndEvidenceLevelOrderBySortOrderAsc(
				eq(roadmapId), eq("MILESTONE_COMPLETED"),
				eq(PageRequest.of(0, ContextRetrievalService.MAX_COMPLETED_MILESTONES)));
	}

	@Test
	void blocksTopicStateWhenActiveTopicScopeDiffers() {
		UUID owner = UUID.randomUUID();
		UUID conversation = UUID.randomUUID();
		UUID topicId = UUID.randomUUID();

		CoachingTopicEntity topic = topic(topicId, "full_swing", "driver", "wood", null);
		when(topics.findFirstByOwnerContextIdAndStatus(owner, "ACTIVE"))
				.thenReturn(Optional.of(topic));

		ContextSelection selection = service.retrieve(owner, conversation, IRON_REQUEST, "질문");

		assertThat(selection.coachingContext().activeTopic()).isNull();
		assertThat(selection.coachingContext().roadmap()).isNull();
		assertThat(selection.coachingContext().pendingOpenLoop()).isNull();
		assertThat(selection.coachingContext().recognition().unrecognizedProgressEvents()).isEmpty();
		verifyNoInteractions(roadmaps, openLoops, progressEvents);
	}

	@Test
	void capsRecentDialogueAtTwelveAndRemovesCurrentMessage() {
		UUID owner = UUID.randomUUID();
		UUID conversation = UUID.randomUUID();
		String current = "현재 사용자 메시지";

		List<ChatMessageEntity> newestFirst = new ArrayList<>();
		newestFirst.add(new ChatMessageEntity(conversation, null, "user", current, null));
		for (int index = 1; index <= 12; index++) {
			newestFirst.add(new ChatMessageEntity(conversation, null, "assistant", "이전 " + index, null));
		}
		when(messages.findByConversationIdOrderBySequenceNumberDesc(eq(conversation), any()))
				.thenReturn(newestFirst);

		ContextSelection selection = service.retrieve(owner, conversation, IRON_REQUEST, current);

		assertThat(selection.recentDialogue()).hasSize(ContextRetrievalService.MAX_RECENT_DIALOGUE);
		assertThat(selection.recentDialogue())
				.extracting(m -> m.content())
				.doesNotContain(current);
	}

	@Test
	void returnsEmptySelectionWhenNoStateExists() {
		UUID owner = UUID.randomUUID();
		UUID conversation = UUID.randomUUID();

		ContextSelection selection = service.retrieve(owner, conversation, IRON_REQUEST, "질문");

		assertThat(selection.coachingContext().activeTopic()).isNull();
		assertThat(selection.coachingContext().roadmap()).isNull();
		assertThat(selection.coachingContext().pendingOpenLoop()).isNull();
		assertThat(selection.coachingContext().facts()).isEmpty();
		assertThat(selection.coachingContext().recognition().recentlyRecognizedTopics()).isEmpty();
		assertThat(selection.coachingContext().recognition().lastRoadmapRevealAt()).isNull();
		assertThat(selection.recentDialogue()).isEmpty();
		assertThat(selection.messageSequenceStart()).isNull();
		assertThat(selection.messageSequenceEnd()).isNull();
	}

	@Test
	void limitsUserContextFactsToTwelve() {
		UUID owner = UUID.randomUUID();
		UUID conversation = UUID.randomUUID();

		List<UserContextFactEntity> many = new ArrayList<>();
		for (int index = 0; index < 15; index++) {
			many.add(fact("full_swing", "7-iron", "iron", null));
		}
		when(facts.findByOwnerContextIdAndSupersededAtIsNullOrderByValidFromDesc(owner))
				.thenReturn(many);

		ContextSelection selection = service.retrieve(owner, conversation, IRON_REQUEST, "질문");

		assertThat(selection.coachingContext().facts())
				.hasSize(ContextRetrievalService.MAX_USER_CONTEXT_FACTS);
	}

	// --- entity mock builders -------------------------------------------------

	private static CoachingTopicEntity topic(
			UUID id, String shotProfile, String club, String clubGroup, String shortGameType) {
		CoachingTopicEntity topic = mock(CoachingTopicEntity.class);
		when(topic.id()).thenReturn(id);
		when(topic.version()).thenReturn(2);
		when(topic.userProblem()).thenReturn("당겨 친다");
		when(topic.shotProfile()).thenReturn(shotProfile);
		when(topic.club()).thenReturn(club);
		when(topic.clubGroup()).thenReturn(clubGroup);
		when(topic.shortGameType()).thenReturn(shortGameType);
		return topic;
	}

	private static RoadmapEntity roadmap(UUID id, UUID currentMilestoneId) {
		RoadmapEntity roadmap = mock(RoadmapEntity.class);
		when(roadmap.id()).thenReturn(id);
		when(roadmap.version()).thenReturn(1);
		when(roadmap.targetSwing()).thenReturn("반복 가능한 스윙");
		when(roadmap.currentMilestoneId()).thenReturn(currentMilestoneId);
		return roadmap;
	}

	private static RoadmapMilestoneEntity milestone(UUID id) {
		RoadmapMilestoneEntity milestone = mock(RoadmapMilestoneEntity.class);
		when(milestone.id()).thenReturn(id);
		when(milestone.version()).thenReturn(2);
		when(milestone.title()).thenReturn("전환 공간 확보");
		when(milestone.evidenceLevel()).thenReturn("USER_REPORTED_PROGRESS");
		when(milestone.completionCondition()).thenReturn("영상에서도 확인된다");
		return milestone;
	}

	private static OpenLoopEntity openLoop() {
		OpenLoopEntity openLoop = mock(OpenLoopEntity.class);
		when(openLoop.id()).thenReturn(UUID.randomUUID());
		when(openLoop.version()).thenReturn(1);
		when(openLoop.nextSingleChange()).thenReturn("감각 유지");
		when(openLoop.nextVerification()).thenReturn("같은 각도에서 확인");
		return openLoop;
	}

	private static ProgressEventEntity progressEvent(UUID topicId) {
		ProgressEventEntity event = mock(ProgressEventEntity.class);
		when(event.id()).thenReturn(UUID.randomUUID());
		when(event.topicId()).thenReturn(topicId);
		when(event.progressLevel()).thenReturn("RESULT_REPEATED");
		when(event.userSignal()).thenReturn("세 번 반복됨");
		return event;
	}

	private static UserContextFactEntity fact(
			String shotProfile, String club, String clubGroup, String shortGameType) {
		UserContextFactEntity fact = mock(UserContextFactEntity.class);
		when(fact.id()).thenReturn(UUID.randomUUID());
		when(fact.version()).thenReturn(1);
		when(fact.statement()).thenReturn("손이 먼저 내려온다");
		when(fact.evidenceLevel()).thenReturn("USER_REPORTED");
		when(fact.shotProfile()).thenReturn(shotProfile);
		when(fact.club()).thenReturn(club);
		when(fact.clubGroup()).thenReturn(clubGroup);
		when(fact.shortGameType()).thenReturn(shortGameType);
		when(fact.sourceEpisodeIds()).thenReturn(List.of());
		return fact;
	}
}
