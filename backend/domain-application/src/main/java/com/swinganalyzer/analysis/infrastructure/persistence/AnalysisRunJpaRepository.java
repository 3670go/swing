package com.swinganalyzer.analysis.infrastructure.persistence;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface AnalysisRunJpaRepository extends JpaRepository<AnalysisRunEntity, UUID> {

	@Query("""
			select run from AnalysisRunEntity run
			join SwingSessionEntity swing on swing.id = run.swingSessionId
			where swing.ownerContextId = :ownerId and run.status <> 'deleted'
			order by run.createdAt desc
			""")
	List<AnalysisRunEntity> findHistory(@Param("ownerId") UUID ownerId, Pageable pageable);

	@Query("""
			select run from AnalysisRunEntity run
			join SwingSessionEntity swing on swing.id = run.swingSessionId
			where run.id = :runId and swing.ownerContextId = :ownerId and run.status <> 'deleted'
			""")
	Optional<AnalysisRunEntity> findOwnedRun(@Param("runId") UUID runId, @Param("ownerId") UUID ownerId);

	Optional<AnalysisRunEntity> findFirstByConversationIdAndStatusInOrderByCompletedAtDesc(
			UUID conversationId, List<String> statuses);
}
