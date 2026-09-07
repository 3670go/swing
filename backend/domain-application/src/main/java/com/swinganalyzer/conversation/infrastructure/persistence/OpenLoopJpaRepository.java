package com.swinganalyzer.conversation.infrastructure.persistence;

import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface OpenLoopJpaRepository extends JpaRepository<OpenLoopEntity, UUID> {

	Optional<OpenLoopEntity> findFirstByTopicIdAndStateOrderByCreatedAtDesc(UUID topicId, String state);
}
