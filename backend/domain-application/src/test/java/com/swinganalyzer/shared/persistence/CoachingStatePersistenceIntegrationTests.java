package com.swinganalyzer.shared.persistence;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import com.swinganalyzer.analysis.application.model.AiProcessingContract.ContextPacket;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.CoachingTurnPlan;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.EvidenceReference;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.OpenLoopCandidate;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.ProblemReframeCandidate;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.ProgressCandidate;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.RecognitionCandidate;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.ShotContext;
import com.swinganalyzer.conversation.application.CoachingPlanApplicationService;
import com.swinganalyzer.conversation.application.CoachingPlanApplicationService.ApplicationCommand;
import com.swinganalyzer.conversation.application.CoachingPlanApplicationService.ApplicationOutcome;
import com.swinganalyzer.conversation.application.ContextPacketAssembler;
import com.swinganalyzer.conversation.application.ContextRetrievalService;
import com.swinganalyzer.conversation.application.ContextSelection;
import com.swinganalyzer.conversation.application.ContextSnapshotStore;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.ActiveTopic;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.CoachingScope;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.Milestone;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.Recognition;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.Roadmap;
import com.swinganalyzer.conversation.infrastructure.persistence.ConversationEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.ConversationJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.OpenLoopEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.OpenLoopJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.OwnerContextEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.OwnerContextJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.ProgressEventEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.ProgressEventJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.RecognitionEventEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.RecognitionEventJpaRepository;

/**
 * Real-PostgreSQL verification of Session 2/3 Java coaching state: Flyway V1-V5
 * migrated, entities validated ({@code ddl-auto=validate}), JPA round-trips, V5
 * constraints, and Coaching Turn Plan application.
 *
 * <p>Gated on {@code MIGRATION_TEST_JDBC_URL}; requires a disposable PostgreSQL
 * (never H2). Skips cleanly when the env var is absent.
 */
@SpringBootTest(properties = {
		"spring.datasource.url=${MIGRATION_TEST_JDBC_URL}",
		"spring.datasource.username=${MIGRATION_TEST_JDBC_USERNAME}",
		"spring.datasource.password=${MIGRATION_TEST_JDBC_PASSWORD}",
		"spring.jpa.hibernate.ddl-auto=validate",
		"spring.flyway.enabled=true",
		"spring.flyway.baseline-on-migrate=false"
})
@EnabledIfEnvironmentVariable(named = "MIGRATION_TEST_JDBC_URL", matches = ".+")
class CoachingStatePersistenceIntegrationTests {

	private static final ShotContext SHOT = new ShotContext(
			"full_swing", "7-iron", "down_the_line", "right", "posture_correction", null, null, null);
	private static final CoachingScope SCOPE = new CoachingScope("full_swing", "7-iron", "iron", null);

	@Autowired
	private CoachingPlanApplicationService planApplication;
	@Autowired
	private ContextSnapshotStore snapshotStore;
	@Autowired
	private ContextPacketAssembler assembler;
	@Autowired
	private ContextRetrievalService retrieval;
	@Autowired
	private OwnerContextJpaRepository owners;
	@Autowired
	private ConversationJpaRepository conversations;
	@Autowired
	private OpenLoopJpaRepository openLoops;
	@Autowired
	private ProgressEventJpaRepository progressEvents;
	@Autowired
	private RecognitionEventJpaRepository recognitionEvents;
	@Autowired
	private JdbcTemplate jdbc;

	@Test
	void flywayAppliedV1ThroughV5AndEntitiesValidate() {
		String version = jdbc.queryForObject(
				"select max(version) from flyway_schema_history where success = true", String.class);
		assertThat(version).isEqualTo("5");
	}

	@Test
	void appliesReframeProgressRecognitionAndOpenLoopWithVideoEvidence() {
		Seed seed = seedActiveTopicWithRoadmap(2, 2);
		UUID requestId = UUID.randomUUID();
		UUID snapshotId = UUID.randomUUID();
		ContextSelection selection = selection(seed, 2, 2);
		ContextPacket packet = assembler.assemble(snapshotId, "됐다 세 번 연속", SHOT, true, selection);
		snapshotStore.save(snapshotId, requestId, seed.ownerId, seed.conversationId, null, selection, packet);

		CoachingTurnPlan plan = new CoachingTurnPlan(
				null,
				new ProblemReframeCandidate("당겨 친다", "전환 공간 부족", "회전 선행", List.of(observation(0))),
				reframeCurrent(2),
				List.of(),
				new ProgressCandidate(seed.milestoneId, 2, "VIDEO_VERIFIED_PROGRESS", "영상에서도 확인",
						List.of(observation(0))),
				new RecognitionCandidate("전환 공간 확보", "PROGRESS_DECLARATION", "핵심을 잡았다"),
				openLoopCandidate());

		ApplicationOutcome outcome = planApplication.apply(new ApplicationCommand(
				requestId, seed.ownerId, seed.conversationId, null, snapshotId, selection, plan, 1));

		assertThat(outcome.applied()).isTrue();
		assertThat(count("coaching_topics", "id = ? and version = 3 and root_problem = '전환 공간 부족'", seed.topicId))
				.isEqualTo(1);
		assertThat(count("progress_events", "topic_id = ? and progress_level = 'VIDEO_VERIFIED_PROGRESS'",
				seed.topicId)).isEqualTo(1);
		assertThat(count("progress_events", "topic_id = ? and recognized = true", seed.topicId)).isEqualTo(1);
		assertThat(jdbc.queryForObject(
				"select count(*) from recognition_events r join progress_events p on r.progress_event_id = p.id"
						+ " where p.topic_id = ?", Integer.class, seed.topicId)).isEqualTo(1);
		assertThat(count("open_loops", "topic_id = ? and state = 'PENDING'", seed.topicId)).isEqualTo(1);
		assertThat(count("coaching_request_applications", "request_id = ? and applied = true", requestId))
				.isEqualTo(1);
		assertThat(count("context_snapshots", "request_id = ?", requestId)).isEqualTo(1);
	}

	@Test
	void blocksOnVersionMismatchAndRecordsBlockedReasonWithoutStateChange() {
		Seed seed = seedActiveTopicWithRoadmap(2, 2);
		UUID requestId = UUID.randomUUID();
		UUID snapshotId = UUID.randomUUID();
		ContextSelection selection = selection(seed, 2, 2);
		saveSnapshot(seed, requestId, snapshotId, selection);
		CoachingTurnPlan plan = new CoachingTurnPlan(null, null, null, List.of(),
				new ProgressCandidate(seed.milestoneId, 99, "RESULT_REPEATED", "결과 반복",
						List.of(message())),
				null, null);

		ApplicationOutcome outcome = planApplication.apply(new ApplicationCommand(
				requestId, seed.ownerId, seed.conversationId, null, snapshotId, selection, plan, 0));

		assertThat(outcome.applied()).isFalse();
		assertThat(outcome.blockedReason()).isEqualTo("VERSION_MISMATCH");
		assertThat(count("progress_events", "topic_id = ?", seed.topicId)).isZero();
		assertThat(count("coaching_request_applications",
				"request_id = ? and applied = false and blocked_reason = 'VERSION_MISMATCH'", requestId))
				.isEqualTo(1);
	}

	@Test
	void doesNotApplyTheSameRequestIdTwice() {
		Seed seed = seedActiveTopicWithRoadmap(2, 2);
		UUID requestId = UUID.randomUUID();
		UUID snapshotId = UUID.randomUUID();
		ContextSelection selection = selection(seed, 2, 2);
		saveSnapshot(seed, requestId, snapshotId, selection);
		CoachingTurnPlan plan = new CoachingTurnPlan(null, null, null, List.of(), null, null,
				openLoopCandidate());
		ApplicationCommand command = new ApplicationCommand(
				requestId, seed.ownerId, seed.conversationId, null, snapshotId, selection, plan, 0);

		planApplication.apply(command);
		ApplicationOutcome second = planApplication.apply(command);

		assertThat(second.applied()).isFalse();
		assertThat(second.blockedReason()).isEqualTo("DUPLICATE_REQUEST_ID");
		assertThat(count("open_loops", "topic_id = ? and state = 'PENDING'", seed.topicId)).isEqualTo(1);
	}

	@Test
	void invalidEvidenceDoesNotCreateProgress() {
		Seed seed = seedActiveTopicWithRoadmap(2, 2);
		UUID requestId = UUID.randomUUID();
		UUID snapshotId = UUID.randomUUID();
		ContextSelection selection = selection(seed, 2, 2);
		saveSnapshot(seed, requestId, snapshotId, selection);
		EvidenceReference unknown = new EvidenceReference("PROGRESS_EVENT", UUID.randomUUID().toString());
		CoachingTurnPlan plan = new CoachingTurnPlan(null, null, null, List.of(),
				new ProgressCandidate(seed.milestoneId, 2, "RESULT_REPEATED", "결과", List.of(unknown)),
				null, null);

		ApplicationOutcome outcome = planApplication.apply(new ApplicationCommand(
				requestId, seed.ownerId, seed.conversationId, null, snapshotId, selection, plan, 0));

		assertThat(outcome.applied()).isTrue();
		assertThat(outcome.progressApplied()).isFalse();
		assertThat(count("progress_events", "topic_id = ?", seed.topicId)).isZero();
	}

	@Test
	void userReportedEvidenceIsNotPromotedToConfirmedVideoProgress() {
		Seed seed = seedActiveTopicWithRoadmap(2, 2);
		UUID requestId = UUID.randomUUID();
		UUID snapshotId = UUID.randomUUID();
		ContextSelection selection = selection(seed, 2, 2);
		saveSnapshot(seed, requestId, snapshotId, selection);
		CoachingTurnPlan plan = new CoachingTurnPlan(null, null, null, List.of(),
				new ProgressCandidate(seed.milestoneId, 2, "VIDEO_VERIFIED_PROGRESS", "느낌", List.of(message())),
				null, null);

		ApplicationOutcome outcome = planApplication.apply(new ApplicationCommand(
				requestId, seed.ownerId, seed.conversationId, null, snapshotId, selection, plan, 0));

		assertThat(outcome.progressApplied()).isFalse();
		assertThat(count("progress_events", "topic_id = ?", seed.topicId)).isZero();
	}

	@Test
	void replacesPriorPendingOpenLoopKeepingExactlyOnePending() {
		Seed seed = seedActiveTopicWithRoadmap(2, 2);
		openLoops.save(new OpenLoopEntity(
				seed.ownerId, seed.topicId, "이전 느낌", "이전 변경", "이전 검증", "이전 완료", null, null));
		UUID requestId = UUID.randomUUID();
		UUID snapshotId = UUID.randomUUID();
		ContextSelection selection = selection(seed, 2, 2);
		saveSnapshot(seed, requestId, snapshotId, selection);
		CoachingTurnPlan plan = new CoachingTurnPlan(null, null, null, List.of(), null, null,
				openLoopCandidate());

		planApplication.apply(new ApplicationCommand(
				requestId, seed.ownerId, seed.conversationId, null, snapshotId, selection, plan, 0));

		assertThat(count("open_loops", "topic_id = ? and state = 'PENDING'", seed.topicId)).isEqualTo(1);
		assertThat(count("open_loops", "topic_id = ? and state = 'REPLACED'", seed.topicId)).isEqualTo(1);
	}

	@Test
	void secondPendingOpenLoopForSameTopicViolatesUniqueIndex() {
		Seed seed = seedActiveTopicWithRoadmap(2, 2);
		openLoops.saveAndFlush(new OpenLoopEntity(
				seed.ownerId, seed.topicId, null, "변경", "검증", "완료", null, null));

		assertThatThrownBy(() -> openLoops.saveAndFlush(new OpenLoopEntity(
				seed.ownerId, seed.topicId, null, "변경2", "검증2", "완료2", null, null)))
				.isInstanceOf(DataIntegrityViolationException.class);
	}

	@Test
	void secondRecognitionForSameProgressEventViolatesUniqueIndex() {
		Seed seed = seedActiveTopicWithRoadmap(2, 2);
		ProgressEventEntity progress = progressEvents.saveAndFlush(new ProgressEventEntity(
				seed.ownerId, seed.topicId, seed.milestoneId, "RESULT_REPEATED", "신호"));
		recognitionEvents.saveAndFlush(new RecognitionEventEntity(
				seed.ownerId, seed.topicId, progress.id(), null, seed.milestoneId, 2,
				"SPECIFIC_RECOGNITION", "대상", "내용"));

		assertThatThrownBy(() -> recognitionEvents.saveAndFlush(new RecognitionEventEntity(
				seed.ownerId, seed.topicId, progress.id(), null, seed.milestoneId, 2,
				"SPECIFIC_RECOGNITION", "대상2", "내용2")))
				.isInstanceOf(DataIntegrityViolationException.class);
	}

	@Test
	void contextRetrievalReadsSeededStateFromPostgres() {
		Seed seed = seedActiveTopicWithRoadmap(3, 2);
		openLoops.save(new OpenLoopEntity(
				seed.ownerId, seed.topicId, "느낌", "변경", "검증", "완료", "결과", "질문?"));

		ContextSelection selection = retrieval.retrieve(seed.ownerId, seed.conversationId, SHOT, "질문");

		assertThat(selection.coachingContext().activeTopic()).isNotNull();
		assertThat(selection.coachingContext().activeTopic().version()).isEqualTo(3);
		assertThat(selection.coachingContext().roadmap()).isNotNull();
		assertThat(selection.coachingContext().roadmap().currentMilestone().milestoneId())
				.isEqualTo(seed.milestoneId);
		assertThat(selection.coachingContext().pendingOpenLoop()).isNotNull();
	}

	@Test
	void snapshotJsonRoundTripsAndDuplicateRequestIdIsRejected() {
		Seed seed = seedActiveTopicWithRoadmap(2, 2);
		UUID requestId = UUID.randomUUID();
		UUID snapshotId = UUID.randomUUID();
		ContextSelection selection = selection(seed, 2, 2);
		ContextPacket packet = assembler.assemble(snapshotId, "질문", SHOT, false, selection);
		snapshotStore.save(snapshotId, requestId, seed.ownerId, seed.conversationId, null, selection, packet);

		Map<String, Object> stored = jdbc.queryForObject(
				"select context_packet_json from context_snapshots where request_id = ?",
				(rs, rowNum) -> readJson(rs.getString(1)), requestId);
		assertThat(stored.get("context_snapshot_id")).isEqualTo(snapshotId.toString());

		assertThatThrownBy(() -> snapshotStore.save(
				UUID.randomUUID(), requestId, seed.ownerId, seed.conversationId, null, selection, packet))
				.isInstanceOf(DataIntegrityViolationException.class);
	}

	@Test
	void applyRollsBackWhileSnapshotStaysCommittedOnDbError() {
		Seed seed = seedActiveTopicWithRoadmap(2, 2);
		UUID requestId = UUID.randomUUID();
		UUID snapshotId = UUID.randomUUID();
		UUID missingMilestoneId = UUID.randomUUID();
		// The snapshot points at the real (seeded) roadmap, so it commits. The plan's
		// progress targets a milestone version that passes the version guard from the
		// snapshot, but whose row does not exist, so the progress INSERT hits an FK and
		// the whole apply() rolls back.
		ContextSelection selection = new ContextSelection(
				new RetrievedCoachingContext(
						new ActiveTopic(seed.topicId, 2, "당겨 친다", null, SCOPE, null, null, null),
						new Roadmap(seed.roadmapId, 1, "목표",
								new Milestone(missingMilestoneId, 2, "M", "USER_REPORTED_PROGRESS", "완료"),
								List.of(), null),
						List.of(), null, Recognition.empty()),
				List.of(), null, null);
		ContextPacket packet = assembler.assemble(snapshotId, "질문", SHOT, true, selection);
		snapshotStore.save(snapshotId, requestId, seed.ownerId, seed.conversationId, null, selection, packet);

		CoachingTurnPlan plan = new CoachingTurnPlan(null, null, null, List.of(),
				new ProgressCandidate(missingMilestoneId, 2, "VIDEO_VERIFIED_PROGRESS", "신호",
						List.of(observation(0))),
				null, null);

		assertThatThrownBy(() -> planApplication.apply(new ApplicationCommand(
				requestId, seed.ownerId, seed.conversationId, null, snapshotId, selection, plan, 1)))
				.isInstanceOf(DataIntegrityViolationException.class);

		// Snapshot committed in its own transaction; the whole apply() rolled back.
		assertThat(count("context_snapshots", "request_id = ?", requestId)).isEqualTo(1);
		assertThat(count("progress_events", "topic_id = ?", seed.topicId)).isZero();
		assertThat(count("coaching_request_applications", "request_id = ?", requestId)).isZero();
	}

	// --- seeding & helpers ----------------------------------------------------

	private record Seed(UUID ownerId, UUID conversationId, UUID topicId, UUID roadmapId, UUID milestoneId) {
	}

	private Seed seedActiveTopicWithRoadmap(int topicVersion, int milestoneVersion) {
		Seed base = seedTopic(topicVersion);
		UUID roadmapId = UUID.randomUUID();
		UUID milestoneId = UUID.randomUUID();
		jdbc.update("insert into roadmaps (id, owner_context_id, topic_id, target_swing, version, is_active)"
				+ " values (?,?,?,?,?,true)", roadmapId, base.ownerId, base.topicId, "반복 가능한 스윙", 1);
		jdbc.update("insert into roadmap_milestones (id, roadmap_id, sort_order, title, completion_condition,"
				+ " evidence_level, version) values (?,?,?,?,?,?,?)",
				milestoneId, roadmapId, 1, "전환 공간", "영상에서도 확인", "USER_REPORTED_PROGRESS", milestoneVersion);
		jdbc.update("update roadmaps set current_milestone_id = ? where id = ?", milestoneId, roadmapId);
		return new Seed(base.ownerId, base.conversationId, base.topicId, roadmapId, milestoneId);
	}

	private Seed seedTopic(int topicVersion) {
		UUID ownerId = owners.save(new OwnerContextEntity("hash-" + UUID.randomUUID())).id();
		UUID conversationId = conversations.save(new ConversationEntity(ownerId)).id();
		UUID topicId = UUID.randomUUID();
		jdbc.update("insert into coaching_topics (id, owner_context_id, status, user_problem, shot_profile,"
				+ " club, club_group, version) values (?,?,?,?,?,?,?,?)",
				topicId, ownerId, "ACTIVE", "당겨 친다", "full_swing", "7-iron", "iron", topicVersion);
		return new Seed(ownerId, conversationId, topicId, null, null);
	}

	private void saveSnapshot(Seed seed, UUID requestId, UUID snapshotId, ContextSelection selection) {
		ContextPacket packet = assembler.assemble(snapshotId, "질문", SHOT, false, selection);
		snapshotStore.save(snapshotId, requestId, seed.ownerId, seed.conversationId, null, selection, packet);
	}

	private ContextSelection selection(Seed seed, int topicVersion, int milestoneVersion) {
		RetrievedCoachingContext coaching = new RetrievedCoachingContext(
				new ActiveTopic(seed.topicId, topicVersion, "당겨 친다", null, SCOPE, null, null, null),
				new Roadmap(seed.roadmapId, 1, "반복 가능한 스윙",
						new Milestone(seed.milestoneId, milestoneVersion, "전환 공간", "USER_REPORTED_PROGRESS",
								"완료 조건"),
						List.of(), null),
				List.of(), null, Recognition.empty());
		return new ContextSelection(coaching, List.of(), null, null);
	}

	private com.swinganalyzer.analysis.application.model.AiProcessingContract.CoachingTopicCandidate reframeCurrent(
			int expectedVersion) {
		var scope = new com.swinganalyzer.analysis.application.model.AiProcessingContract.CoachingScope(
				"full_swing", "7-iron", "iron", null);
		return new com.swinganalyzer.analysis.application.model.AiProcessingContract.CoachingTopicCandidate(
				"REFRAME_CURRENT", null, expectedVersion, scope, "전환 공간 확보");
	}

	private static OpenLoopCandidate openLoopCandidate() {
		return new OpenLoopCandidate("느낌", "감각 유지", "같은 각도 확인", "영상 확인", "결과", "다음 영상 언제?");
	}

	private static EvidenceReference observation(int index) {
		return new EvidenceReference("OBSERVATION", "observation:" + index);
	}

	private static EvidenceReference message() {
		return new EvidenceReference("MESSAGE", "current-user-message");
	}

	private int count(String table, String whereClause, Object... args) {
		return jdbc.queryForObject("select count(*) from " + table + " where " + whereClause,
				Integer.class, args);
	}

	@SuppressWarnings("unchecked")
	private static Map<String, Object> readJson(String json) {
		try {
			return new tools.jackson.databind.json.JsonMapper().readValue(json, Map.class);
		} catch (Exception error) {
			throw new IllegalStateException(error);
		}
	}
}
