package com.swinganalyzer.conversation.application;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.swinganalyzer.conversation.application.MemberProfileService.ProfileFact;
import com.swinganalyzer.conversation.application.MemberProfileService.ProfileSnapshot;
import com.swinganalyzer.conversation.application.MemberProfileService.ProfileUpdate;
import com.swinganalyzer.conversation.infrastructure.persistence.OwnerContextEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.OwnerContextJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.UserContextFactEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.UserContextFactJpaRepository;
import com.swinganalyzer.shared.error.PublicApiException;

@Service
public class MemberProfileService {

	private static final Duration INJURY_EXPIRATION = Duration.ofDays(90);
	private static final Set<String> PROFILE_FACT_TYPES = Set.of(
			"BODY_TRAIT", "INJURY", "CURRENT_SWING_STYLE", "TARGET_SWING_STYLE");

	private final OwnerContextJpaRepository owners;
	private final UserContextFactJpaRepository facts;

	public MemberProfileService(
			OwnerContextJpaRepository owners,
			UserContextFactJpaRepository facts) {
		this.owners = owners;
		this.facts = facts;
	}

	@Transactional(readOnly = true)
	public ProfileSnapshot get(UUID ownerContextId) {
		OwnerContextEntity owner = findOwner(ownerContextId);
		return snapshot(owner, activeProfileFacts(ownerContextId));
	}

	@Transactional
	public ProfileSnapshot update(UUID ownerContextId, ProfileUpdate update) {
		OwnerContextEntity owner = findOwner(ownerContextId);
		owner.updateProfile(normalize(update.displayName()), normalize(update.defaultHandedness()));

		List<UserContextFactEntity> previous = activeProfileFacts(ownerContextId);
		Instant now = Instant.now();
		previous.forEach(fact -> fact.supersede(now));

		List<UserContextFactEntity> replacements = new ArrayList<>();
		addFact(replacements, ownerContextId, "CURRENT_SWING_STYLE", null,
				update.currentSwingStyle(), null);
		addFact(replacements, ownerContextId, "TARGET_SWING_STYLE", null,
				update.targetSwingStyle(), null);
		for (ProfileFactInput bodyTrait : update.bodyTraits()) {
			addFact(replacements, ownerContextId, "BODY_TRAIT", bodyTrait.bodyRegion(),
					bodyTrait.statement(), null);
		}
		for (ProfileFactInput injury : update.injuries()) {
			addFact(replacements, ownerContextId, "INJURY", injury.bodyRegion(),
					injury.statement(), now.plus(INJURY_EXPIRATION));
		}

		owners.save(owner);
		facts.saveAll(previous);
		facts.saveAll(replacements);
		return snapshot(owner, replacements);
	}

	private OwnerContextEntity findOwner(UUID ownerContextId) {
		return owners.findById(ownerContextId)
				.orElseThrow(() -> new PublicApiException(HttpStatus.NOT_FOUND, "MEMBER_NOT_FOUND"));
	}

	private List<UserContextFactEntity> activeProfileFacts(UUID ownerContextId) {
		Instant now = Instant.now();
		return facts.findByOwnerContextIdAndSupersededAtIsNullOrderByValidFromDesc(ownerContextId)
				.stream()
				.filter(fact -> PROFILE_FACT_TYPES.contains(fact.factType()))
				.filter(fact -> fact.expiresAt() == null || fact.expiresAt().isAfter(now))
				.toList();
	}

	private static void addFact(
			List<UserContextFactEntity> target,
			UUID ownerContextId,
			String factType,
			String bodyRegion,
			String statement,
			Instant expiresAt) {
		String normalizedStatement = normalize(statement);
		if (normalizedStatement == null) {
			return;
		}
		target.add(new UserContextFactEntity(
				ownerContextId,
				factType,
				normalize(bodyRegion),
				normalizedStatement,
				null,
				null,
				null,
				null,
				null,
				expiresAt));
	}

	private static ProfileSnapshot snapshot(
			OwnerContextEntity owner,
			List<UserContextFactEntity> profileFacts) {
		String currentSwingStyle = latestStatement(profileFacts, "CURRENT_SWING_STYLE");
		String targetSwingStyle = latestStatement(profileFacts, "TARGET_SWING_STYLE");
		List<ProfileFact> bodyTraits = profileFacts.stream()
				.filter(fact -> "BODY_TRAIT".equals(fact.factType()))
				.map(MemberProfileService::toProfileFact)
				.toList();
		List<ProfileFact> injuries = profileFacts.stream()
				.filter(fact -> "INJURY".equals(fact.factType()))
				.map(MemberProfileService::toProfileFact)
				.toList();
		return new ProfileSnapshot(
				owner.id(),
				owner.displayName(),
				owner.defaultHandedness(),
				currentSwingStyle,
				targetSwingStyle,
				bodyTraits,
				injuries);
	}

	private static String latestStatement(List<UserContextFactEntity> facts, String factType) {
		return facts.stream()
				.filter(fact -> factType.equals(fact.factType()))
				.map(UserContextFactEntity::statement)
				.findFirst()
				.orElse(null);
	}

	private static ProfileFact toProfileFact(UserContextFactEntity fact) {
		return new ProfileFact(fact.bodyRegion(), fact.statement(), fact.expiresAt());
	}

	private static String normalize(String value) {
		if (value == null || value.isBlank()) {
			return null;
		}
		return value.strip();
	}

	public record ProfileUpdate(
			String displayName,
			String defaultHandedness,
			String currentSwingStyle,
			String targetSwingStyle,
			List<ProfileFactInput> bodyTraits,
			List<ProfileFactInput> injuries) {
	}

	public record ProfileFactInput(String bodyRegion, String statement) {
	}

	public record ProfileFact(String bodyRegion, String statement, Instant expiresAt) {
	}

	public record ProfileSnapshot(
			UUID ownerContextId,
			String displayName,
			String defaultHandedness,
			String currentSwingStyle,
			String targetSwingStyle,
			List<ProfileFact> bodyTraits,
			List<ProfileFact> injuries) {
	}
}
