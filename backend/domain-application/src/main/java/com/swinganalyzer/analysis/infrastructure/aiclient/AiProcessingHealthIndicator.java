package com.swinganalyzer.analysis.infrastructure.aiclient;

import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.HealthIndicator;

import com.swinganalyzer.analysis.application.AiProcessingClient;
import com.swinganalyzer.analysis.application.AiProcessingClientException;

public final class AiProcessingHealthIndicator implements HealthIndicator {

	private final AiProcessingClient client;

	public AiProcessingHealthIndicator(AiProcessingClient client) {
		this.client = client;
	}

	@Override
	public Health health() {
		try {
			var response = client.health();
			if ("ready".equals(response.status()) && response.modelConfigured()) {
				return Health.up().withDetail("service", response.service()).build();
			}
			return Health.down()
					.withDetail("service", response.service())
					.withDetail("status", response.status())
					.build();
		} catch (AiProcessingClientException error) {
			return Health.down().withDetail("code", error.code()).build();
		}
	}
}
