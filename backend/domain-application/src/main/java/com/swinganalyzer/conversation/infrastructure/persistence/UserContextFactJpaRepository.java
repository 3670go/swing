package com.swinganalyzer.conversation.infrastructure.persistence;

import java.util.List;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface UserContextFactJpaRepository extends JpaRepository<UserContextFactEntity, UUID> {

	List<UserContextFactEntity> findByOwnerContextIdAndSupersededAtIsNullOrderByValidFromDesc(
			UUID ownerContextId);
}
