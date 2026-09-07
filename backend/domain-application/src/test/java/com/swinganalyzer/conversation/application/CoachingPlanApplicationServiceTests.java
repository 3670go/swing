package com.swinganalyzer.conversation.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import com.swinganalyzer.analysis.application.model.AiProcessingContract.CoachingTurnPlan;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.EvidenceReference;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.OpenLoopCandidate;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.ProgressCandidate;
import com.swinganalyzer.conversation.application.CoachingPlanApplicationService.ApplicationCommand;
import com.swinganalyzer.conversation.application.CoachingPlanApplicationService.ApplicationOutcome;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.ActiveTopic;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.CoachingScope;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.Milestone;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.Recognition;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.Roadmap;
import com.swinganalyzer.conversation.infrastructure.persistence.CoachingRequestApplicationEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.CoachingRequestApplicationJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.CoachingTopicJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.OpenLoopEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.OpenLoopJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.ProgressEventJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.RecognitionEventJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.RoadmapMilestoneJpaRepository;

class CoachingPlanApplicationServiceTests {

	private final CoachingRequestApplicationJpaRepository applications =
			mock(CoachingRequestApplicationJpaRepository.class);
	private final CoachingTopicJpaRepository topics = mock(CoachingTopicJpaRepository.class);
	private final RoadmapMilestoneJpaRepository milestones = mock(RoadmapMilestoneJpaRepository.class);
	private final ProgressEventJpaRepository progressEvents = mock(ProgressEventJpaRepository.class);
	private final RecognitionEventJpaRepository recognitionEvents = mock(RecognitionEventJpaRepository.class);
	private final OpenLoopJpaRepository openLoops = mock(OpenLoopJpaRepository.class);

	private final CoachingPlanApplicationService service = new CoachingPlanApplicationService(
			applications, topics, milestones, progressEvents, recognitionEvents, openLoops);

	private final UUID requestId = UUID.randomUUID();
	private final UUID owner = UUID.randomUUID();
	private final UUID conversation = UUID.randomUUID();
	private final UUID snapshot = UUID.randomUUID();
	private final UUID topicId = UUID.randomUUID();
	private final UUID milestoneId = UUID.randomUUID();

	@Test
	void doesNotApplyTwiceForTheSameRequestId() {
		when(applications.existsById(requestId)).thenReturn(true);

		ApplicationOutcome outcome = service.apply(command(
				planWithOpenLoop(), selection(2, 2), 0));

		assertThat(outcome.applied()).isFalse();
		assertThat(outcome.blockedReason()).isEqualTo("DUPLICATE_REQUEST_ID");
		verify(applications, never()).save(any());
		verifyNoInteractions(openLoops, progressEvents, recognitionEvents, milestones, topics);
	}

	@Test
	void blocksWholeRequestWhenExpectedVersionDiffers() {
		CoachingTurnPlan plan = planWithProgress(
				progress(milestoneId, 99, "RESULT_REPEATED", List.of(message())));

		ApplicationOutcome outcome = service.apply(command(plan, selection(2, 2), 0));

		assertThat(outcome.applied()).isFalse();
		assertThat(outcome.blockedReason()).isEqualTo("VERSION_MISMATCH");
		verify(progressEvents, never()).save(any());
		ArgumentCaptor<CoachingRequestApplicationEntity> saved =
				ArgumentCaptor.forClass(CoachingRequestApplicationEntity.class);
		verify(applications).save(saved.capture());
		assertThat(saved.getValue().applied()).isFalse();
		assertThat(saved.getValue().blockedReason()).isEqualTo("VERSION_MISMATCH");
	}

	@Test
	void skipsCandidateWhenEvidenceReferenceIsNotInThePacket() {
		EvidenceReference unknown = new EvidenceReference("PROGRESS_EVENT", UUID.randomUUID().toString());
		CoachingTurnPlan plan = planWithProgress(
				progress(milestoneId, 2, "RESULT_REPEATED", List.of(unknown)));

		ApplicationOutcome outcome = service.apply(command(plan, selection(2, 2), 0));

		assertThat(outcome.applied()).isTrue();
		assertThat(outcome.progressApplied()).isFalse();
		verify(progressEvents, never()).save(any());
	}

	@Test
	void doesNotPromoteUserReportedEvidenceToConfirmedVideoProgress() {
		CoachingTurnPlan plan = planWithProgress(
				progress(milestoneId, 2, "VIDEO_VERIFIED_PROGRESS", List.of(message())));

		ApplicationOutcome outcome = service.apply(command(plan, selection(2, 2), 0));

		assertThat(outcome.applied()).isTrue();
		assertThat(outcome.progressApplied()).isFalse();
		verify(progressEvents, never()).save(any());
	}

	@Test
	void keepsASinglePendingOpenLoopPerTopic() {
		OpenLoopEntity existing = new OpenLoopEntity(
				owner, topicId, "이전 느낌", "이전 변경", "이전 검증", "이전 완료", null, null);
		when(openLoops.findFirstByTopicIdAndStateOrderByCreatedAtDesc(topicId, "PENDING"))
				.thenReturn(Optional.of(existing));

		ApplicationOutcome outcome = service.apply(command(planWithOpenLoop(), selection(2, 2), 0));

		assertThat(outcome.openLoopApplied()).isTrue();
		assertThat(existing.state()).isEqualTo("REPLACED");
		// The prior loop's REPLACED update is flushed before the new PENDING insert so
		// PostgreSQL never sees two PENDING rows for the topic.
		verify(openLoops).saveAndFlush(existing);
		verify(openLoops).save(any());
	}

	// --- builders -------------------------------------------------------------

	private ApplicationCommand command(CoachingTurnPlan plan, ContextSelection selection, int observationCount) {
		return new ApplicationCommand(
				requestId, owner, conversation, null, snapshot, selection, plan, observationCount);
	}

	private ContextSelection selection(int topicVersion, int milestoneVersion) {
		CoachingScope scope = new CoachingScope("full_swing", "7-iron", "iron", null);
		ActiveTopic topic = new ActiveTopic(topicId, topicVersion, "당겨 친다", null, scope, null, null, null);
		Roadmap roadmap = new Roadmap(
				UUID.randomUUID(), 1, "반복 가능한 스윙",
				new Milestone(milestoneId, milestoneVersion, "전환 공간", "USER_REPORTED_PROGRESS", "완료 조건"),
				List.of(), null);
		RetrievedCoachingContext coaching = new RetrievedCoachingContext(
				topic, roadmap, List.of(), null, Recognition.empty());
		return new ContextSelection(coaching, List.of(), null, null);
	}

	private static EvidenceReference message() {
		return new EvidenceReference("MESSAGE", "current-user-message");
	}

	private static ProgressCandidate progress(
			UUID milestoneId, int expectedVersion, String level, List<EvidenceReference> refs) {
		return new ProgressCandidate(milestoneId, expectedVersion, level, "세 번 반복됨", refs);
	}

	private static CoachingTurnPlan planWithProgress(ProgressCandidate progress) {
		return new CoachingTurnPlan(null, null, null, List.of(), progress, null, null);
	}

	private static CoachingTurnPlan planWithOpenLoop() {
		OpenLoopCandidate openLoop = new OpenLoopCandidate(
				"손이 먼저 내려오는 느낌", "감각 유지", "같은 각도 확인", "영상에서도 확인", null, "다음 영상 언제?");
		return new CoachingTurnPlan(null, null, null, List.of(), null, null, openLoop);
	}
}
