package com.swinganalyzer.conversation.api;

import java.util.UUID;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.swinganalyzer.conversation.application.OwnerAccountService;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

@RestController
@RequestMapping("/v1/me")
public class MemberApi {

	private final OwnerAccountService owners;

	public MemberApi(OwnerAccountService owners) {
		this.owners = owners;
	}

	@PostMapping("/claim")
	ClaimResponse claim(@AuthenticationPrincipal Jwt jwt, @Valid @RequestBody ClaimRequest request) {
		return new ClaimResponse(owners.claim(request.anonymousSessionId(), jwt.getSubject()));
	}

	public record ClaimRequest(
			@NotBlank @Size(min = 16, max = 128) String anonymousSessionId) {
	}

	public record ClaimResponse(UUID ownerContextId) {
	}
}
