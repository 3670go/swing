package com.swinganalyzer.analysis.infrastructure.aiclient;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.boot.health.contributor.Status;

import com.swinganalyzer.analysis.application.AiProcessingClient;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.HealthResponse;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.InternalAnalysisRequest;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.InternalAnalysisResponse;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.InternalTextCoachingRequest;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.InternalTextCoachingResponse;

class AiProcessingHealthIndicatorTests {

	@Test
	void reportsUpOnlyForReadyConfiguredPythonService() {
		var indicator = new AiProcessingHealthIndicator(new StubClient());

		var health = indicator.health();

		assertEquals(Status.UP, health.getStatus());
		assertEquals("ai-processing", health.getDetails().get("service"));
	}

	private static final class StubClient implements AiProcessingClient {

		@Override
		public HealthResponse health() {
			return new HealthResponse("ai-processing", "ready", true);
		}

		@Override
		public InternalAnalysisResponse analyze(InternalAnalysisRequest request) {
			throw new UnsupportedOperationException();
		}

		@Override
		public InternalTextCoachingResponse coachText(InternalTextCoachingRequest request) {
			throw new UnsupportedOperationException();
		}
	}
}
