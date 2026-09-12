package com.swinganalyzer.conversation.infrastructure.persistence;

import java.util.List;
import java.util.UUID;

import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface RoadmapMilestoneJpaRepository extends JpaRepository<RoadmapMilestoneEntity, UUID> {

	List<RoadmapMilestoneEntity> findByRoadmapIdOrderBySortOrderAsc(UUID roadmapId);

	List<RoadmapMilestoneEntity> findByRoadmapIdAndEvidenceLevelOrderBySortOrderAsc(
			UUID roadmapId, String evidenceLevel, Pageable pageable);
}
