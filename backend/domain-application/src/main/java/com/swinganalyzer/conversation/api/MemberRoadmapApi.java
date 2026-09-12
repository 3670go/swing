package com.swinganalyzer.conversation.api;

import java.util.UUID;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.swinganalyzer.conversation.application.MemberRoadmapService;
import com.swinganalyzer.conversation.application.MemberRoadmapService.RoadmapView;
import com.swinganalyzer.conversation.application.OwnerAccountService;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

@RestController
@RequestMapping("/v1/me/roadmaps")
public class MemberRoadmapApi {

	private final OwnerAccountService owners;
	private final MemberRoadmapService roadmaps;

	public MemberRoadmapApi(OwnerAccountService owners, MemberRoadmapService roadmaps) {
		this.owners = owners;
		this.roadmaps = roadmaps;
	}

	@PostMapping
	RoadmapView create(
			@AuthenticationPrincipal Jwt jwt,
			@Valid @RequestBody CreateRoadmapRequest request) {
		return roadmaps.create(
				owners.resolveAuthenticated(jwt.getSubject()),
				request.analysisRunId(),
				request.targetSwing());
	}

	@GetMapping("/active")
	ActiveRoadmapResponse active(@AuthenticationPrincipal Jwt jwt) {
		return new ActiveRoadmapResponse(
				roadmaps.active(owners.resolveAuthenticated(jwt.getSubject())));
	}

	public record CreateRoadmapRequest(
			@NotNull UUID analysisRunId,
			@NotBlank @Size(max = 500) String targetSwing) {
	}

	public record ActiveRoadmapResponse(RoadmapView roadmap) {
	}
}
