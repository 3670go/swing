package com.swinganalyzer.conversation.api;

import java.util.List;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.swinganalyzer.conversation.application.MemberProfileService;
import com.swinganalyzer.conversation.application.MemberProfileService.ProfileFactInput;
import com.swinganalyzer.conversation.application.MemberProfileService.ProfileSnapshot;
import com.swinganalyzer.conversation.application.MemberProfileService.ProfileUpdate;
import com.swinganalyzer.conversation.application.OwnerAccountService;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

@RestController
@RequestMapping("/v1/me/profile")
public class MemberProfileApi {

	private final OwnerAccountService owners;
	private final MemberProfileService profiles;

	public MemberProfileApi(OwnerAccountService owners, MemberProfileService profiles) {
		this.owners = owners;
		this.profiles = profiles;
	}

	@GetMapping
	ProfileSnapshot get(@AuthenticationPrincipal Jwt jwt) {
		return profiles.get(owners.resolveAuthenticated(jwt.getSubject()));
	}

	@PutMapping
	ProfileSnapshot update(
			@AuthenticationPrincipal Jwt jwt,
			@Valid @RequestBody ProfileUpdateRequest request) {
		return profiles.update(
				owners.resolveAuthenticated(jwt.getSubject()),
				new ProfileUpdate(
						request.displayName(),
						request.defaultHandedness(),
						request.currentSwingStyle(),
						request.targetSwingStyle(),
						request.bodyTraits().stream().map(ProfileFactRequest::toInput).toList(),
						request.injuries().stream().map(ProfileFactRequest::toInput).toList()));
	}

	public record ProfileUpdateRequest(
			@Size(max = 80) String displayName,
			@Pattern(regexp = "right|left") String defaultHandedness,
			@Size(max = 500) String currentSwingStyle,
			@Size(max = 500) String targetSwingStyle,
			@Size(max = 10) List<@Valid ProfileFactRequest> bodyTraits,
			@Size(max = 10) List<@Valid ProfileFactRequest> injuries) {
		public ProfileUpdateRequest {
			bodyTraits = bodyTraits == null ? List.of() : List.copyOf(bodyTraits);
			injuries = injuries == null ? List.of() : List.copyOf(injuries);
		}
	}

	public record ProfileFactRequest(
			@Size(max = 64) String bodyRegion,
			@NotBlank @Size(max = 500) String statement) {
		ProfileFactInput toInput() {
			return new ProfileFactInput(bodyRegion, statement);
		}
	}
}
