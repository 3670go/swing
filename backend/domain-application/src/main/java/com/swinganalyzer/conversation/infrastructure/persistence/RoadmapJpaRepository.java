package com.swinganalyzer.conversation.infrastructure.persistence;

import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface RoadmapJpaRepository extends JpaRepository<RoadmapEntity, UUID> {

	Optional<RoadmapEntity> findFirstByTopicIdAndActiveTrue(UUID topicId);

	Optional<RoadmapEntity> findFirstByOwnerContextIdAndActiveTrue(UUID ownerContextId);
}
