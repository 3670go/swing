package com.swinganalyzer.conversation.application;

import java.util.UUID;

import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.swinganalyzer.conversation.infrastructure.persistence.OwnerContextEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.OwnerContextJpaRepository;
import com.swinganalyzer.shared.error.PublicApiException;

@Service
public class OwnerAccountService {

	private static final String SUPABASE_PROVIDER = "supabase";

	private final OwnerContextJpaRepository owners;

	public OwnerAccountService(OwnerContextJpaRepository owners) {
		this.owners = owners;
	}

	@Transactional
	public UUID resolve(String anonymousSessionId, String authenticatedSubject) {
		if (authenticatedSubject == null) {
			return getOrCreateAnonymous(anonymousSessionId).id();
		}
		return claim(anonymousSessionId, authenticatedSubject);
	}

	@Transactional
	public UUID resolveAuthenticated(String authenticatedSubject) {
		return owners.findByExternalProviderAndExternalSubject(SUPABASE_PROVIDER, authenticatedSubject)
				.orElseGet(() -> owners.save(
						OwnerContextEntity.authenticated(SUPABASE_PROVIDER, authenticatedSubject)))
				.id();
	}

	@Transactional
	public UUID claim(String anonymousSessionId, String authenticatedSubject) {
		OwnerContextEntity anonymousOwner = owners
				.findByAnonymousSessionHash(ConversationStore.hashAnonymousSession(anonymousSessionId))
				.orElse(null);
		OwnerContextEntity authenticatedOwner = owners
				.findByExternalProviderAndExternalSubject(SUPABASE_PROVIDER, authenticatedSubject)
				.orElse(null);

		if (authenticatedOwner != null) {
			if (anonymousOwner == null || authenticatedOwner.id().equals(anonymousOwner.id())) {
				return authenticatedOwner.id();
			}
			throw conflict();
		}
		if (anonymousOwner == null) {
			return owners.save(OwnerContextEntity.authenticated(SUPABASE_PROVIDER, authenticatedSubject)).id();
		}
		if (anonymousOwner.externalSubject() != null
				&& !authenticatedSubject.equals(anonymousOwner.externalSubject())) {
			throw conflict();
		}
		try {
			anonymousOwner.claim(SUPABASE_PROVIDER, authenticatedSubject);
			return owners.saveAndFlush(anonymousOwner).id();
		} catch (DataIntegrityViolationException error) {
			throw conflict();
		}
	}

	private OwnerContextEntity getOrCreateAnonymous(String anonymousSessionId) {
		String hash = ConversationStore.hashAnonymousSession(anonymousSessionId);
		return owners.findByAnonymousSessionHash(hash)
				.orElseGet(() -> owners.save(new OwnerContextEntity(hash)));
	}

	private static PublicApiException conflict() {
		return new PublicApiException(HttpStatus.CONFLICT, "OWNER_CLAIM_CONFLICT");
	}
}
