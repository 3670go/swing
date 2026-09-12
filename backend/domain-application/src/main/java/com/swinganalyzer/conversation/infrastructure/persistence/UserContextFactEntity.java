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
 * Java-owned user context fact stored in {@code user_context_facts}.
 */
@Entity
@Table(name = "user_context_facts")
public class UserContextFactEntity {

	@Id
	private UUID id;

	@Column(name = "owner_context_id", nullable = false)
	private UUID ownerContextId;

	@Column(name = "source_type", nullable = false, length = 32)
	private String sourceType;

	@Column(nullable = false)
	private int version;

	@Column(name = "evidence_level", nullable = false, length = 32)
	private String evidenceLevel;

	@Column(name = "fact_type", length = 32)
	private String factType;

	@Column(name = "body_region", length = 64)
	private String bodyRegion;

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

	@Column(name = "source_message_id")
	private UUID sourceMessageId;

	@Column(name = "valid_from", nullable = false)
	private Instant validFrom;

	@Column(name = "superseded_at")
	private Instant supersededAt;

	@Column(name = "expires_at")
	private Instant expiresAt;

	protected UserContextFactEntity() {
	}

	public UserContextFactEntity(
			UUID ownerContextId,
			String factType,
			String bodyRegion,
			String statement,
			String shotProfile,
			String club,
			String clubGroup,
			String shortGameType,
			UUID sourceMessageId,
			Instant expiresAt) {
		this.id = UUID.randomUUID();
		this.ownerContextId = ownerContextId;
		this.sourceType = "USER_EXPLICIT";
		this.version = 1;
		this.evidenceLevel = "USER_REPORTED";
		this.factType = factType;
		this.bodyRegion = bodyRegion;
		this.statement = statement;
		this.shotProfile = shotProfile;
		this.club = club;
		this.clubGroup = clubGroup;
		this.shortGameType = shortGameType;
		this.sourceMessageId = sourceMessageId;
		this.sourceEpisodeIds = List.of();
		this.validFrom = Instant.now();
		this.expiresAt = expiresAt;
	}

	public void refresh(String statement, UUID sourceMessageId, Instant expiresAt) {
		this.statement = statement;
		this.sourceMessageId = sourceMessageId;
		this.expiresAt = expiresAt;
		this.validFrom = Instant.now();
		this.version = this.version + 1;
	}

	public void supersede(Instant at) {
		this.supersededAt = at;
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

	public String factType() {
		return factType;
	}

	public String bodyRegion() {
		return bodyRegion;
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

	public Instant expiresAt() {
		return expiresAt;
	}
}
