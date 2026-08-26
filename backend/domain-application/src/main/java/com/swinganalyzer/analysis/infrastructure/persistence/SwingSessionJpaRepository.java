package com.swinganalyzer.analysis.infrastructure.persistence;

import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface SwingSessionJpaRepository extends JpaRepository<SwingSessionEntity, UUID> {

	Optional<SwingSessionEntity> findByIdAndOwnerContextId(UUID id, UUID ownerContextId);
}
