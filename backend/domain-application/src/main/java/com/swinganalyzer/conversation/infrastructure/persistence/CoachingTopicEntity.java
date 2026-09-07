package com.swinganalyzer.conversation.infrastructure.persistence;

import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/**
 * Read mapping for the {@code coaching_topics} table (V5). Session 2 reads only;
 * the Flyway V5 migration owns the schema and all constraints.
 */
@Entity
@Table(name = "coaching_topics")
public class CoachingTopicEntity {

	@Id
	private UUID id;

	@Column(name = "owner_context_id", nullable = false)
	private UUID ownerContextId;

	@Column(nullable = false)
	private int version;

	@Column(nullable = false, length = 32)
	private String status;

	@Column(name = "user_problem", nullable = false, columnDefinition = "text")
	private String userProblem;

	@Column(name = "root_problem", columnDefinition = "text")
	private String rootProblem;

	@Column(name = "shot_profile", nullable = false, length = 32)
	private String shotProfile;

	@Column(length = 64)
	private String club;

	@Column(name = "club_group", length = 64)
	private String clubGroup;

	@Column(name = "short_game_type", length = 64)
	private String shortGameType;

	@Column(name = "active_hypothesis", columnDefinition = "text")
	private String activeHypothesis;

	@Column(name = "current_experiment", columnDefinition = "text")
	private String currentExperiment;

	@Column(name = "carry_forward_feel", columnDefinition = "text")
	private String carryForwardFeel;

	protected CoachingTopicEntity() {
	}

	/** Reframes the root problem and bumps the aggregate version (Session 3). */
	public void reframe(String newRootProblem) {
		this.rootProblem = newRootProblem;
		this.version = this.version + 1;
	}

	public UUID id() {
		return id;
	}

	public UUID ownerContextId() {
		return ownerContextId;
	}

	public int version() {
		return version;
	}

	public String status() {
		return status;
	}

	public String userProblem() {
		return userProblem;
	}

	public String rootProblem() {
		return rootProblem;
	}

	public String shotProfile() {
		return shotProfile;
	}

	public String club() {
		return club;
	}

	public String clubGroup() {
		return clubGroup;
	}

	public String shortGameType() {
		return shortGameType;
	}

	public String activeHypothesis() {
		return activeHypothesis;
	}

	public String currentExperiment() {
		return currentExperiment;
	}

	public String carryForwardFeel() {
		return carryForwardFeel;
	}
}
