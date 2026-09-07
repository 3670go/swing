package com.swinganalyzer.conversation.infrastructure.persistence;

import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CoachingTopicJpaRepository extends JpaRepository<CoachingTopicEntity, UUID> {

	Optional<CoachingTopicEntity> findFirstByOwnerContextIdAndStatus(UUID ownerContextId, String status);
}
