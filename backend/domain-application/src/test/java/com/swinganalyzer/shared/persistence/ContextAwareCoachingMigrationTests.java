package com.swinganalyzer.shared.persistence;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.UUID;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

@EnabledIfEnvironmentVariable(named = "MIGRATION_TEST_JDBC_URL", matches = ".+")
class ContextAwareCoachingMigrationTests {

	private final String jdbcUrl = System.getenv("MIGRATION_TEST_JDBC_URL");
	private final String username = System.getenv("MIGRATION_TEST_JDBC_USERNAME");
	private final String password = System.getenv("MIGRATION_TEST_JDBC_PASSWORD");

	@BeforeEach
	void migrateSchema() throws SQLException {
		Flyway flyway = flyway();
		flyway.clean();
		prepareStorageSchema();
		flyway.migrate();
	}

	@Test
	void appliesV1ThroughV7WithoutRecreatingObjectsOnSecondMigrationRun() throws SQLException {
		Integer installedRank = queryInteger("""
				select installed_rank
				from flyway_schema_history
				where version = '7'
				""");

		assertThat(installedRank).isNotNull();
		assertThat(flyway().migrate().migrationsExecuted).isZero();
	}

	@Test
	void rejectsBlockedReasonWhenRequestApplicationWasApplied() throws SQLException {
		UUID ownerId = createOwner();

		assertThatThrownBy(() -> execute("""
				insert into coaching_request_applications (
					request_id,
					owner_context_id,
					applied,
					blocked_reason
				)
				values (?, ?, true, 'VERSION_MISMATCH')
				""", UUID.randomUUID(), ownerId))
				.isInstanceOf(SQLException.class);
	}

	@Test
	void rejectsMissingBlockedReasonWhenRequestApplicationWasBlocked() throws SQLException {
		UUID ownerId = createOwner();

		assertThatThrownBy(() -> execute("""
				insert into coaching_request_applications (
					request_id,
					owner_context_id,
					applied,
					blocked_reason
				)
				values (?, ?, false, null)
				""", UUID.randomUUID(), ownerId))
				.isInstanceOf(SQLException.class);
	}

	@Test
	void rejectsCurrentMilestoneFromDifferentRoadmap() throws SQLException {
		UUID firstRoadmapId = createRoadmap(createOwner(), "first target");
		UUID secondRoadmapId = createRoadmap(createOwner(), "second target");
		UUID secondRoadmapMilestoneId = createMilestone(secondRoadmapId, 1);

		assertThatThrownBy(() -> execute("""
				update roadmaps
				set current_milestone_id = ?
				where id = ?
				""", secondRoadmapMilestoneId, firstRoadmapId))
				.isInstanceOf(SQLException.class);
	}

	@Test
	void rejectsSecondActiveRoadmapForSameOwner() throws SQLException {
		UUID ownerId = createOwner();
		createRoadmap(ownerId, "first target");

		assertThatThrownBy(() -> createRoadmap(ownerId, "second target"))
				.isInstanceOf(SQLException.class);
	}

	@Test
	void rejectsSecondActiveTopicForSameOwner() throws SQLException {
		UUID ownerId = createOwner();
		createTopic(ownerId, "ACTIVE", "first active");

		assertThatThrownBy(() -> createTopic(ownerId, "ACTIVE", "second active"))
				.isInstanceOf(SQLException.class);
	}

	@Test
	void rejectsSecondPendingOpenLoopForSameTopic() throws SQLException {
		UUID ownerId = createOwner();
		UUID topicId = createTopic(ownerId, "ACTIVE", "active topic");
		createOpenLoop(ownerId, topicId, "PENDING");

		assertThatThrownBy(() -> createOpenLoop(ownerId, topicId, "PENDING"))
				.isInstanceOf(SQLException.class);
	}

	@Test
	void rejectsSecondRecognitionForSameProgressEvent() throws SQLException {
		UUID ownerId = createOwner();
		UUID topicId = createTopic(ownerId, "ACTIVE", "active topic");
		UUID progressEventId = createProgressEvent(ownerId, topicId);
		createRecognition(ownerId, topicId, progressEventId, "first recognition");

		assertThatThrownBy(() -> createRecognition(ownerId, topicId, progressEventId,
				"second recognition"))
				.isInstanceOf(SQLException.class);
	}

	private Flyway flyway() {
		return Flyway.configure()
				.cleanDisabled(false)
				.dataSource(jdbcUrl, username, password)
				.locations("classpath:db/migration")
				.load();
	}

	private void prepareStorageSchema() throws SQLException {
		try (Connection connection = connection();
				Statement statement = connection.createStatement()) {
			statement.execute("CREATE SCHEMA IF NOT EXISTS storage");
			statement.execute("""
					CREATE TABLE IF NOT EXISTS storage.buckets (
						id text PRIMARY KEY,
						name text,
						public boolean,
						file_size_limit bigint,
						allowed_mime_types text[]
					)
					""");
		}
	}

	private UUID createOwner() throws SQLException {
		return queryUuid("""
				insert into owner_contexts (anonymous_session_hash)
				values (?)
				returning id
				""", "owner-" + UUID.randomUUID());
	}

	private UUID createTopic(UUID ownerId, String status, String userProblem) throws SQLException {
		return queryUuid("""
				insert into coaching_topics (
					owner_context_id,
					status,
					user_problem,
					shot_profile,
					club_group
				)
				values (?, ?, ?, 'full_swing', 'iron')
				returning id
				""", ownerId, status, userProblem);
	}

	private UUID createRoadmap(UUID ownerId, String targetSwing) throws SQLException {
		return queryUuid("""
				insert into roadmaps (
					owner_context_id,
					target_swing
				)
				values (?, ?)
				returning id
				""", ownerId, targetSwing);
	}

	private UUID createMilestone(UUID roadmapId, int sortOrder) throws SQLException {
		return queryUuid("""
				insert into roadmap_milestones (
					roadmap_id,
					sort_order,
					title,
					completion_condition
				)
				values (?, ?, ?, 'same camera angle verifies the change')
				returning id
				""", roadmapId, sortOrder, "milestone " + sortOrder);
	}

	private UUID createProgressEvent(UUID ownerId, UUID topicId) throws SQLException {
		return queryUuid("""
				insert into progress_events (
					owner_context_id,
					topic_id,
					progress_level,
					user_signal
				)
				values (?, ?, 'RESULT_REPEATED', 'three shots repeated the result')
				returning id
				""", ownerId, topicId);
	}

	private UUID createOpenLoop(UUID ownerId, UUID topicId, String state) throws SQLException {
		return queryUuid("""
				insert into open_loops (
					owner_context_id,
					topic_id,
					state,
					next_single_change,
					next_verification,
					completion_condition
				)
				values (
					?,
					?,
					?,
					'keep the same feel',
					'compare the same camera angle',
					'verify the hand position change'
				)
				returning id
				""", ownerId, topicId, state);
	}

	private UUID createRecognition(UUID ownerId, UUID topicId, UUID progressEventId, String content)
			throws SQLException {
		return queryUuid("""
				insert into recognition_events (
					owner_context_id,
					topic_id,
					progress_event_id,
					intensity,
					target,
					recognition_content
				)
				values (?, ?, ?, 'SPECIFIC_RECOGNITION', 'transition space', ?)
				returning id
				""", ownerId, topicId, progressEventId, content);
	}

	private Integer queryInteger(String sql) throws SQLException {
		try (Connection connection = connection();
				PreparedStatement statement = connection.prepareStatement(sql);
				ResultSet resultSet = statement.executeQuery()) {
			if (!resultSet.next()) {
				return null;
			}
			return resultSet.getInt(1);
		}
	}

	private UUID queryUuid(String sql, Object... values) throws SQLException {
		try (Connection connection = connection();
				PreparedStatement statement = connection.prepareStatement(sql)) {
			bind(statement, values);
			try (ResultSet resultSet = statement.executeQuery()) {
				if (!resultSet.next()) {
					throw new SQLException("No UUID returned");
				}
				return resultSet.getObject(1, UUID.class);
			}
		}
	}

	private void execute(String sql, Object... values) throws SQLException {
		try (Connection connection = connection();
				PreparedStatement statement = connection.prepareStatement(sql)) {
			bind(statement, values);
			statement.executeUpdate();
		}
	}

	private Connection connection() throws SQLException {
		return DriverManager.getConnection(jdbcUrl, username, password);
	}

	private static void bind(PreparedStatement statement, Object... values) throws SQLException {
		for (int index = 0; index < values.length; index++) {
			statement.setObject(index + 1, values[index]);
		}
	}
}
