package com.swinganalyzer.analysis.infrastructure.aiclient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import com.swinganalyzer.analysis.application.AiProcessingClient;
import com.swinganalyzer.analysis.application.AiProcessingClientException;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.InternalAnalysisRequest;

import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.json.JsonMapper;

@SpringBootTest(properties = {
		"ai-processing.enabled=true",
		"ai-processing.base-url=http://127.0.0.1:8001",
		"ai-processing.token=internal-smoke-test-token",
		"ai-processing.timeout-seconds=10"
})
@EnabledIfEnvironmentVariable(named = "RUN_AI_PROCESSING_INTEGRATION", matches = "true")
class LiveAiProcessingIntegrationTests {

	@Autowired
	private AiProcessingClient client;

	@Test
	void javaClientReachesPythonAnalysisErrorContractWithoutProviderCall() throws Exception {
		String fixture = Files.readString(
				Path.of("..", "contracts", "fixtures", "analysis-request.json"));
		var mapper = JsonMapper.builder()
				.propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
				.build();
		InternalAnalysisRequest request = mapper.readValue(fixture, InternalAnalysisRequest.class);

		AiProcessingClientException error = assertThrows(
				AiProcessingClientException.class,
				() -> client.analyze(request));

		assertEquals("MEDIA_UNAVAILABLE", error.code());
		assertEquals(request.requestId(), error.requestId());
		assertEquals(request.analysisRunId(), error.analysisRunId());
	}
}
