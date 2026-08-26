package com.swinganalyzer.media.infrastructure.persistence;

import java.time.Instant;
import java.util.UUID;

import org.hibernate.annotations.CreationTimestamp;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;

@Entity
@Table(name = "media_assets", indexes = {
		@Index(name = "ix_media_assets_session_id", columnList = "session_id"),
		@Index(name = "ix_media_assets_status", columnList = "status")
})
public class MediaAssetEntity {

	@Id
	@GeneratedValue
	private UUID id;

	@Column(name = "session_id", nullable = false)
	private UUID sessionId;

	@Column(nullable = false, length = 32)
	private String kind;

	@Column(name = "storage_path", nullable = false, unique = true, columnDefinition = "text")
	private String storagePath;

	@Column(length = 64)
	private String sha256;

	@Column(name = "duration_ms")
	private Long durationMs;

	private Integer width;

	private Integer height;

	@Column(nullable = false, length = 32)
	private String status;

	@CreationTimestamp
	@Column(name = "created_at", nullable = false, updatable = false)
	private Instant createdAt;

	protected MediaAssetEntity() {
	}

	public MediaAssetEntity(UUID id, UUID sessionId, String kind, String storagePath, String sha256,
			String status) {
		this.id = id;
		this.sessionId = sessionId;
		this.kind = kind;
		this.storagePath = storagePath;
		this.sha256 = sha256;
		this.status = status;
	}

	public void markDeleted() {
		this.status = "deleted";
	}

	public UUID id() {
		return id;
	}

	public UUID sessionId() {
		return sessionId;
	}

	public String storagePath() {
		return storagePath;
	}

	public String status() {
		return status;
	}
}
