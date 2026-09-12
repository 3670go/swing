package com.swinganalyzer.conversation.infrastructure.persistence;

import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ConversationJpaRepository extends JpaRepository<ConversationEntity, UUID> {

	Optional<ConversationEntity> findByIdAndOwnerContextId(UUID id, UUID ownerContextId);

	Optional<ConversationEntity> findFirstByOwnerContextIdOrderByUpdatedAtDesc(UUID ownerContextId);
}
