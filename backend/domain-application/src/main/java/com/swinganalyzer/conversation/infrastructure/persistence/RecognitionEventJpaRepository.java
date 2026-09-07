package com.swinganalyzer.conversation.infrastructure.persistence;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface RecognitionEventJpaRepository extends JpaRepository<RecognitionEventEntity, UUID> {

	List<RecognitionEventEntity> findByOwnerContextIdOrderByExposedAtDesc(
			UUID ownerContextId, Pageable pageable);

	Optional<RecognitionEventEntity> findFirstByOwnerContextIdAndRoadmapIdIsNotNullOrderByExposedAtDesc(
			UUID ownerContextId);
}
