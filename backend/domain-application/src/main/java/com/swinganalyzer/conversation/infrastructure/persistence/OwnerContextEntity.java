package com.swinganalyzer.conversation.infrastructure.persistence;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

import org.hibernate.annotations.CreationTimestamp;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(name = "owner_contexts", uniqueConstraints = {
		@UniqueConstraint(name = "uq_owner_contexts_external_subject", columnNames = { "external_provider", "external_subject" })
})
public class OwnerContextEntity {

	@Id
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
		this.id = UUID.randomUUID();
		this.anonymousSessionHash = anonymousSessionHash;
	}

	public static OwnerContextEntity authenticated(String provider, String subject) {
		OwnerContextEntity owner = new OwnerContextEntity();
		owner.id = UUID.randomUUID();
		owner.externalProvider = provider;
		owner.externalSubject = subject;
		owner.claimedAt = Instant.now();
		return owner;
	}

	public void claim(String provider, String subject) {
		if (externalSubject != null
				&& (!Objects.equals(externalSubject, subject) || !Objects.equals(externalProvider, provider))) {
			throw new IllegalStateException("Owner context already belongs to another identity");
		}
		this.externalProvider = provider;
		this.externalSubject = subject;
		this.claimedAt = Instant.now();
	}

	public void updateProfile(String displayName, String defaultHandedness) {
		this.displayName = displayName;
		this.defaultHandedness = defaultHandedness;
	}

	public UUID id() {
		return id;
	}

	public String anonymousSessionHash() {
		return anonymousSessionHash;
	}

	public String externalProvider() {
		return externalProvider;
	}

	public String externalSubject() {
		return externalSubject;
	}

	public String displayName() {
		return displayName;
	}

	public String defaultHandedness() {
		return defaultHandedness;
	}

	public Instant claimedAt() {
		return claimedAt;
	}
}
