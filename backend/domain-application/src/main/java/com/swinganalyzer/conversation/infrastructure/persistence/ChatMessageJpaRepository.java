package com.swinganalyzer.conversation.infrastructure.persistence;

import java.util.List;
import java.util.UUID;

import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ChatMessageJpaRepository extends JpaRepository<ChatMessageEntity, UUID> {

	List<ChatMessageEntity> findByConversationIdOrderByCreatedAtDesc(UUID conversationId, Pageable pageable);
}
