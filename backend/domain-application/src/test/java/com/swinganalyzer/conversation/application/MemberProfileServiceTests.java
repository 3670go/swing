package com.swinganalyzer.conversation.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

import org.junit.jupiter.api.Test;

import com.swinganalyzer.conversation.application.MemberProfileService.ProfileFactInput;
import com.swinganalyzer.conversation.application.MemberProfileService.ProfileSnapshot;
import com.swinganalyzer.conversation.application.MemberProfileService.ProfileUpdate;
import com.swinganalyzer.conversation.infrastructure.persistence.OwnerContextEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.OwnerContextJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.UserContextFactEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.UserContextFactJpaRepository;

class MemberProfileServiceTests {

	@Test
	void returnsOnlyCurrentUnexpiredProfileFacts() {
		Fixture fixture = new Fixture();
		UserContextFactEntity currentStyle = fixture.fact(
				"CURRENT_SWING_STYLE", null, "페이드", null);
		UserContextFactEntity activeInjury = fixture.fact(
				"INJURY", "왼쪽 손목", "통증 있음", Instant.now().plusSeconds(3600));
		UserContextFactEntity expiredInjury = fixture.fact(
				"INJURY", "허리", "예전 통증", Instant.now().minusSeconds(1));
		when(fixture.facts.findByOwnerContextIdAndSupersededAtIsNullOrderByValidFromDesc(fixture.owner.id()))
				.thenReturn(List.of(currentStyle, activeInjury, expiredInjury));

		ProfileSnapshot profile = fixture.service.get(fixture.owner.id());

		assertThat(profile.currentSwingStyle()).isEqualTo("페이드");
		assertThat(profile.injuries()).extracting(MemberProfileService.ProfileFact::statement)
				.containsExactly("통증 있음");
	}

	@Test
	void replacesProfileFactsAndAppliesNinetyDayInjuryExpiry() {
		Fixture fixture = new Fixture();
		UserContextFactEntity previous = fixture.fact(
				"TARGET_SWING_STYLE", null, "낮은 탄도", null);
		when(fixture.facts.findByOwnerContextIdAndSupersededAtIsNullOrderByValidFromDesc(fixture.owner.id()))
				.thenReturn(List.of(previous));

		Instant before = Instant.now().plusSeconds(89L * 24 * 60 * 60);
		ProfileSnapshot profile = fixture.service.update(
				fixture.owner.id(),
				new ProfileUpdate(
						"홍길동",
						"right",
						"페이드",
						"스트레이트",
						List.of(new ProfileFactInput("상체", "회전이 빠름")),
						List.of(new ProfileFactInput("왼쪽 손목", "통증 있음"))));

		assertThat(previous.supersededAt()).isNotNull();
		assertThat(profile.displayName()).isEqualTo("홍길동");
		assertThat(profile.defaultHandedness()).isEqualTo("right");
		assertThat(profile.currentSwingStyle()).isEqualTo("페이드");
		assertThat(profile.targetSwingStyle()).isEqualTo("스트레이트");
		assertThat(profile.bodyTraits()).extracting(MemberProfileService.ProfileFact::statement)
				.containsExactly("회전이 빠름");
		assertThat(profile.injuries()).singleElement().satisfies(injury -> {
			assertThat(injury.bodyRegion()).isEqualTo("왼쪽 손목");
			assertThat(injury.expiresAt()).isAfter(before);
		});
		verify(fixture.owners).save(fixture.owner);
		verify(fixture.facts).saveAll(List.of(previous));
	}

	private static final class Fixture {
		final OwnerContextJpaRepository owners = mock(OwnerContextJpaRepository.class);
		final UserContextFactJpaRepository facts = mock(UserContextFactJpaRepository.class);
		final OwnerContextEntity owner = OwnerContextEntity.authenticated("supabase", "subject-1");
		final MemberProfileService service = new MemberProfileService(owners, facts);

		Fixture() {
			when(owners.findById(owner.id())).thenReturn(Optional.of(owner));
		}

		UserContextFactEntity fact(String type, String bodyRegion, String statement, Instant expiresAt) {
			return new UserContextFactEntity(
					owner.id(), type, bodyRegion, statement, null, null, null, null, null, expiresAt);
		}
	}
}
