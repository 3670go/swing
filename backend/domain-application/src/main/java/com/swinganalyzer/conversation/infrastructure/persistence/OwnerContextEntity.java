package com.swinganalyzer.conversation.infrastructure.persistence;

import java.time.Instant;
import java.util.UUID;

import org.hibernate.annotations.CreationTimestamp;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(name = "owner_contexts", uniqueConstraints = {
		@UniqueConstraint(name = "uq_owner_contexts_external_subject", columnNames = { "external_provider", "external_subject" })
})
public class OwnerContextEntity {

	@Id
	@GeneratedValue
	private UUID id;

	@Column(name = "anonymous_session_hash", unique = true, columnDefinition = "text")
	private String anonymousSessionHash;

	@Column(name = "external_provider", columnDefinition = "text")
	private String externalProvider;

	@Column(name = "external_subject", columnDefinition = "text")
	private String externalSubject;

	@Column(name = "display_name", columnDefinition = "text")
	private String displayName;

	@Column(name = "default_handedness", length = 16)
	private String defaultHandedness;

	@Column(name = "claimed_at")
	private Instant claimedAt;

	@CreationTimestamp
	@Column(name = "created_at", nullable = false, updatable = false)
	private Instant createdAt;

	protected OwnerContextEntity() {
	}

	public OwnerContextEntity(String anonymousSessionHash) {
		this.anonymousSessionHash = anonymousSessionHash;
	}

	public UUID id() {
		return id;
	}

	public String anonymousSessionHash() {
		return anonymousSessionHash;
	}
}
