package com.swinganalyzer.conversation.infrastructure.persistence;

import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface OwnerContextJpaRepository extends JpaRepository<OwnerContextEntity, UUID> {

	Optional<OwnerContextEntity> findByAnonymousSessionHash(String anonymousSessionHash);

	Optional<OwnerContextEntity> findByExternalProviderAndExternalSubject(
			String externalProvider,
			String externalSubject);
}
