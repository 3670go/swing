package com.swinganalyzer.analysis.infrastructure.aiclient;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.converter.json.JacksonJsonHttpMessageConverter;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import com.swinganalyzer.analysis.application.AiProcessingClientException;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.AnalysisRequest;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.TextCoachingRequest;

import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.json.JsonMapper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class RestAiProcessingClientTests {

	private static final Path FIXTURE_ROOT = Path.of("..", "contracts", "fixtures");

	private JsonMapper objectMapper;
	private MockRestServiceServer server;
	private RestAiProcessingClient client;

	@BeforeEach
	void setUp() {
		objectMapper = JsonMapper.builder()
				.propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
				.build();
		RestClient.Builder builder = RestClient.builder()
				.baseUrl("http://ai-processing.test")
				.defaultHeader(HttpHeaders.AUTHORIZATION, "Bearer internal-test-token")
				.configureMessageConverters(converters -> converters
						.withJsonConverter(new JacksonJsonHttpMessageConverter(objectMapper)));
		server = MockRestServiceServer.bindTo(builder).build();
		client = new RestAiProcessingClient(builder.build(), objectMapper);
	}

	@AfterEach
	void verifyServer() {
		server.verify();
	}

	@Test
	void sendsSharedAnalysisFixtureAndReadsSharedResponse() throws Exception {
		String requestJson = fixture("analysis-request.json");
		String responseJson = fixture("analysis-response.json");
		AnalysisRequest request = objectMapper.readValue(requestJson, AnalysisRequest.class);
		server.expect(requestTo("http://ai-processing.test/internal/v1/analyses"))
				.andExpect(header(HttpHeaders.AUTHORIZATION, "Bearer internal-test-token"))
				.andExpect(content().json(requestJson))
				.andRespond(withSuccess(responseJson, MediaType.APPLICATION_JSON));

		var response = client.analyze(request);

		assertEquals(request.analysisRunId(), response.analysisRunId());
		assertEquals("succeeded", response.status());
		assertEquals("video_ready", response.coachContent().evidenceMode());
	}

	@Test
	void sendsSharedTextCoachingFixtureAndReadsSharedResponse() throws Exception {
		String requestJson = fixture("text-coaching-request.json");
		String responseJson = fixture("text-coaching-response.json");
		TextCoachingRequest request = objectMapper.readValue(requestJson, TextCoachingRequest.class);
		server.expect(requestTo("http://ai-processing.test/internal/v1/coaching/text"))
				.andExpect(content().json(requestJson))
				.andRespond(withSuccess(responseJson, MediaType.APPLICATION_JSON));

		var response = client.coachText(request);

		assertEquals(request.requestId(), response.requestId());
		assertEquals("text_only", response.coachContent().evidenceMode());
	}

	@Test
	void mapsStructuredPythonErrorWithoutRetrying() throws Exception {
		String requestJson = fixture("analysis-request.json");
		AnalysisRequest request = objectMapper.readValue(requestJson, AnalysisRequest.class);
		server.expect(requestTo("http://ai-processing.test/internal/v1/analyses"))
				.andRespond(
						withStatus(HttpStatus.UNPROCESSABLE_CONTENT)
								.contentType(MediaType.APPLICATION_JSON)
								.body(fixture("error-response.json")));

		AiProcessingClientException error = assertThrows(
				AiProcessingClientException.class,
				() -> client.analyze(request));

		assertEquals("MEDIA_DECODE_FAILED", error.code());
		assertEquals(422, error.statusCode());
		assertEquals(false, error.retryable());
	}

	private static String fixture(String name) throws IOException {
		return Files.readString(FIXTURE_ROOT.resolve(name));
	}
}
