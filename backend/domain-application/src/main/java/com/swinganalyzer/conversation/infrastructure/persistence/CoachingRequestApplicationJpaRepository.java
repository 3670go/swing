package com.swinganalyzer.conversation.infrastructure.persistence;

import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CoachingRequestApplicationJpaRepository
		extends JpaRepository<CoachingRequestApplicationEntity, UUID> {
}
