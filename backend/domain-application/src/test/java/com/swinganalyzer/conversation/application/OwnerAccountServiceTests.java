package com.swinganalyzer.conversation.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

import com.swinganalyzer.conversation.infrastructure.persistence.OwnerContextEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.OwnerContextJpaRepository;
import com.swinganalyzer.shared.error.PublicApiException;

class OwnerAccountServiceTests {

	private static final String SESSION_ID = "anonymous-session-0001";
	private static final String SUBJECT = "member-subject-0001";

	@Test
	void reusesExistingAnonymousOwner() {
		OwnerContextJpaRepository owners = mock(OwnerContextJpaRepository.class);
		OwnerContextEntity existing = new OwnerContextEntity(ConversationStore.hashAnonymousSession(SESSION_ID));
		when(owners.findByAnonymousSessionHash(existing.anonymousSessionHash()))
				.thenReturn(Optional.of(existing));

		assertThat(new OwnerAccountService(owners).resolve(SESSION_ID, null)).isEqualTo(existing.id());
		verify(owners, never()).save(any());
	}

	@Test
	void createsAuthenticatedOwnerWhenMemberHasNoPreviousContext() {
		OwnerContextJpaRepository owners = mock(OwnerContextJpaRepository.class);
		when(owners.findByExternalProviderAndExternalSubject("supabase", SUBJECT))
				.thenReturn(Optional.empty());
		when(owners.save(any(OwnerContextEntity.class))).thenAnswer(invocation -> invocation.getArgument(0));

		OwnerAccountService service = new OwnerAccountService(owners);
		assertThat(service.resolve(SESSION_ID, SUBJECT)).isNotNull();
	}

	@Test
	void claimsGuestContextForAuthenticatedMember() {
		OwnerContextJpaRepository owners = mock(OwnerContextJpaRepository.class);
		OwnerContextEntity guest = new OwnerContextEntity(ConversationStore.hashAnonymousSession(SESSION_ID));
		when(owners.findByAnonymousSessionHash(guest.anonymousSessionHash())).thenReturn(Optional.of(guest));
		when(owners.findByExternalProviderAndExternalSubject("supabase", SUBJECT))
				.thenReturn(Optional.empty());
		when(owners.saveAndFlush(guest)).thenReturn(guest);

		assertThat(new OwnerAccountService(owners).claim(SESSION_ID, SUBJECT)).isEqualTo(guest.id());
		assertThat(guest.externalProvider()).isEqualTo("supabase");
		assertThat(guest.externalSubject()).isEqualTo(SUBJECT);
		assertThat(guest.claimedAt()).isNotNull();
	}

	@Test
	void rejectsClaimWhenGuestAndMemberAlreadyOwnDifferentContexts() {
		OwnerContextJpaRepository owners = mock(OwnerContextJpaRepository.class);
		OwnerContextEntity guest = new OwnerContextEntity(ConversationStore.hashAnonymousSession(SESSION_ID));
		OwnerContextEntity member = OwnerContextEntity.authenticated("supabase", SUBJECT);
		when(owners.findByAnonymousSessionHash(guest.anonymousSessionHash())).thenReturn(Optional.of(guest));
		when(owners.findByExternalProviderAndExternalSubject("supabase", SUBJECT))
				.thenReturn(Optional.of(member));

		assertThatThrownBy(() -> new OwnerAccountService(owners).claim(SESSION_ID, SUBJECT))
				.isInstanceOfSatisfying(PublicApiException.class, error -> {
					assertThat(error.status()).isEqualTo(HttpStatus.CONFLICT);
					assertThat(error.detail()).isEqualTo("OWNER_CLAIM_CONFLICT");
				});
	}
}
