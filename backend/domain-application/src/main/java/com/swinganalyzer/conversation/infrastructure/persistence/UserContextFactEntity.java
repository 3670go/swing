package com.swinganalyzer.conversation.infrastructure.persistence;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/**
 * Read mapping for the {@code user_context_facts} table (V5). Session 2 reads only.
 */
@Entity
@Table(name = "user_context_facts")
public class UserContextFactEntity {

	@Id
	private UUID id;

	@Column(name = "owner_context_id", nullable = false)
	private UUID ownerContextId;

	@Column(nullable = false)
	private int version;

	@Column(name = "evidence_level", nullable = false, length = 32)
	private String evidenceLevel;

	@Column(nullable = false, columnDefinition = "text")
	private String statement;

	@Column(name = "shot_profile", length = 32)
	private String shotProfile;

	@Column(length = 64)
	private String club;

	@Column(name = "club_group", length = 64)
	private String clubGroup;

	@Column(name = "short_game_type", length = 64)
	private String shortGameType;

	@JdbcTypeCode(SqlTypes.JSON)
	@Column(name = "source_episode_ids_json", columnDefinition = "jsonb")
	private List<String> sourceEpisodeIds;

	@Column(name = "valid_from", nullable = false)
	private Instant validFrom;

	@Column(name = "superseded_at")
	private Instant supersededAt;

	protected UserContextFactEntity() {
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

	public String evidenceLevel() {
		return evidenceLevel;
	}

	public String statement() {
		return statement;
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

	public List<String> sourceEpisodeIds() {
		return sourceEpisodeIds == null ? List.of() : sourceEpisodeIds;
	}

	public Instant validFrom() {
		return validFrom;
	}

	public Instant supersededAt() {
		return supersededAt;
	}
}
