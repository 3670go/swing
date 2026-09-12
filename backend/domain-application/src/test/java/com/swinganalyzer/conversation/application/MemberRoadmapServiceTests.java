package com.swinganalyzer.conversation.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

import com.swinganalyzer.analysis.infrastructure.persistence.AnalysisRunEntity;
import com.swinganalyzer.analysis.infrastructure.persistence.AnalysisRunJpaRepository;
import com.swinganalyzer.conversation.application.MemberRoadmapService.RoadmapView;
import com.swinganalyzer.conversation.infrastructure.persistence.CoachingTopicEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.CoachingTopicJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.RoadmapEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.RoadmapJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.RoadmapMilestoneEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.RoadmapMilestoneJpaRepository;
import com.swinganalyzer.shared.error.PublicApiException;

class MemberRoadmapServiceTests {

	@Test
	void createsFirstMilestoneFromOwnedSuccessfulAnalysis() {
		Fixture fixture = new Fixture();
		when(fixture.analysisRuns.findOwnedRun(fixture.run.id(), fixture.ownerId))
				.thenReturn(Optional.of(fixture.run));
		when(fixture.topics.findFirstByOwnerContextIdAndStatus(fixture.ownerId, "ACTIVE"))
				.thenReturn(Optional.of(fixture.topic));
		when(fixture.roadmaps.findFirstByTopicIdAndActiveTrue(fixture.topic.id()))
				.thenReturn(Optional.empty());
		when(fixture.roadmaps.findFirstByOwnerContextIdAndActiveTrue(fixture.ownerId))
				.thenReturn(Optional.empty());
		when(fixture.roadmaps.saveAndFlush(any(RoadmapEntity.class)))
				.thenAnswer(invocation -> invocation.getArgument(0));
		when(fixture.milestones.saveAndFlush(any(RoadmapMilestoneEntity.class)))
				.thenAnswer(invocation -> invocation.getArgument(0));

		RoadmapView roadmap = fixture.service.create(
				fixture.ownerId, fixture.run.id(), "일관된 스트레이트 구질");

		assertThat(roadmap.targetSwing()).isEqualTo("일관된 스트레이트 구질");
		assertThat(roadmap.startingState()).isEqualTo("다운스윙 때 당겨 침");
		assertThat(roadmap.currentMilestone().title()).isEqualTo("가슴 회전을 한 박자 늦춘다");
		assertThat(roadmap.currentMilestone().evidenceLevel()).isEqualTo("NOT_STARTED");
		assertThat(roadmap.currentMilestone().completionCondition())
				.isEqualTo("후방 영상에서 손이 내려오는 공간을 확인한다");
	}

	@Test
	void hidesForeignAnalysisAsNotFound() {
		Fixture fixture = new Fixture();
		when(fixture.analysisRuns.findOwnedRun(fixture.run.id(), fixture.ownerId))
				.thenReturn(Optional.empty());

		assertThatThrownBy(() -> fixture.service.create(
				fixture.ownerId, fixture.run.id(), "스트레이트"))
				.isInstanceOfSatisfying(PublicApiException.class, error -> {
					assertThat(error.status()).isEqualTo(HttpStatus.NOT_FOUND);
					assertThat(error.detail()).isEqualTo("ANALYSIS_NOT_FOUND");
				});
	}

	@Test
	void rejectsAnalysisWithoutActionAndVerification() {
		Fixture fixture = new Fixture();
		fixture.run.complete("succeeded", Map.of(), Map.of("content", Map.of()));
		when(fixture.analysisRuns.findOwnedRun(fixture.run.id(), fixture.ownerId))
				.thenReturn(Optional.of(fixture.run));
		when(fixture.topics.findFirstByOwnerContextIdAndStatus(fixture.ownerId, "ACTIVE"))
				.thenReturn(Optional.of(fixture.topic));
		when(fixture.roadmaps.findFirstByTopicIdAndActiveTrue(fixture.topic.id()))
				.thenReturn(Optional.empty());

		assertThatThrownBy(() -> fixture.service.create(
				fixture.ownerId, fixture.run.id(), "스트레이트"))
				.isInstanceOfSatisfying(PublicApiException.class, error -> {
					assertThat(error.status()).isEqualTo(HttpStatus.UNPROCESSABLE_CONTENT);
					assertThat(error.detail()).isEqualTo("ROADMAP_SOURCE_INCOMPLETE");
				});
	}

	@Test
	void archivesPreviousTopicRoadmapBeforeReplacingItsTarget() {
		Fixture fixture = new Fixture();
		RoadmapEntity previous = new RoadmapEntity(
				fixture.ownerId, fixture.topic.id(), "기존 목표", "시작 상태", "확인 조건");
		when(fixture.analysisRuns.findOwnedRun(fixture.run.id(), fixture.ownerId))
				.thenReturn(Optional.of(fixture.run));
		when(fixture.topics.findFirstByOwnerContextIdAndStatus(fixture.ownerId, "ACTIVE"))
				.thenReturn(Optional.of(fixture.topic));
		when(fixture.roadmaps.findFirstByTopicIdAndActiveTrue(fixture.topic.id()))
				.thenReturn(Optional.of(previous));
		when(fixture.roadmaps.saveAndFlush(any(RoadmapEntity.class)))
				.thenAnswer(invocation -> invocation.getArgument(0));
		when(fixture.milestones.saveAndFlush(any(RoadmapMilestoneEntity.class)))
				.thenAnswer(invocation -> invocation.getArgument(0));

		RoadmapView replacement = fixture.service.create(
				fixture.ownerId, fixture.run.id(), "새 목표");

		assertThat(previous.active()).isFalse();
		assertThat(replacement.targetSwing()).isEqualTo("새 목표");
	}

	private static final class Fixture {
		final UUID ownerId = UUID.randomUUID();
		final UUID conversationId = UUID.randomUUID();
		final AnalysisRunJpaRepository analysisRuns = mock(AnalysisRunJpaRepository.class);
		final CoachingTopicJpaRepository topics = mock(CoachingTopicJpaRepository.class);
		final RoadmapJpaRepository roadmaps = mock(RoadmapJpaRepository.class);
		final RoadmapMilestoneJpaRepository milestones = mock(RoadmapMilestoneJpaRepository.class);
		final MemberRoadmapService service = new MemberRoadmapService(
				analysisRuns, topics, roadmaps, milestones);
		final CoachingTopicEntity topic = new CoachingTopicEntity(
				ownerId, conversationId, "다운스윙 때 당겨 침", "full_swing",
				"7번 아이언", null, null);
		final AnalysisRunEntity run = successfulRun();

		private AnalysisRunEntity successfulRun() {
			AnalysisRunEntity created = new AnalysisRunEntity(
					UUID.randomUUID(), conversationId, "video", "test-model");
			created.complete(
					"succeeded",
					Map.of(),
					Map.of("content", Map.of(
							"single_change", "가슴 회전을 한 박자 늦춘다",
							"verification", "후방 영상에서 손이 내려오는 공간을 확인한다")));
			return created;
		}
	}
}
