package com.swinganalyzer.analysis.infrastructure.aiclient;

import java.util.UUID;

import org.springframework.http.HttpStatusCode;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import com.swinganalyzer.analysis.application.AiProcessingClient;
import com.swinganalyzer.analysis.application.AiProcessingClientException;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.ErrorResponse;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.HealthResponse;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.InternalAnalysisRequest;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.InternalAnalysisResponse;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.InternalTextCoachingRequest;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.InternalTextCoachingResponse;

import tools.jackson.databind.ObjectMapper;

public final class RestAiProcessingClient implements AiProcessingClient {

	private final RestClient restClient;
	private final ObjectMapper objectMapper;

	public RestAiProcessingClient(RestClient restClient, ObjectMapper objectMapper) {
		this.restClient = restClient;
		this.objectMapper = objectMapper;
	}

	@Override
	public HealthResponse health() {
		return get("/internal/health", HealthResponse.class);
	}

	@Override
	public InternalAnalysisResponse analyze(InternalAnalysisRequest request) {
		return post("/internal/v1/analyses", request, InternalAnalysisResponse.class);
	}

	@Override
	public InternalTextCoachingResponse coachText(InternalTextCoachingRequest request) {
		return post("/internal/v1/coaching/text", request, InternalTextCoachingResponse.class);
	}

	private <T> T get(String path, Class<T> responseType) {
		try {
			return restClient.get()
					.uri(path)
					.retrieve()
					.onStatus(HttpStatusCode::isError, this::throwInternalError)
					.body(responseType);
		} catch (ResourceAccessException error) {
			throw transportFailure("MODEL_TIMEOUT", "AI Processing request timed out", error);
		} catch (RestClientException error) {
			throw transportFailure("INTERNAL_ERROR", "AI Processing request failed", error);
		}
	}

	private <T> T post(String path, Object requestBody, Class<T> responseType) {
		try {
			return restClient.post()
					.uri(path)
					.body(requestBody)
					.retrieve()
					.onStatus(HttpStatusCode::isError, this::throwInternalError)
					.body(responseType);
		} catch (ResourceAccessException error) {
			throw transportFailure("MODEL_TIMEOUT", "AI Processing request timed out", error);
		} catch (RestClientException error) {
			throw transportFailure("INTERNAL_ERROR", "AI Processing request failed", error);
		}
	}

	private void throwInternalError(
			org.springframework.http.HttpRequest _request,
			org.springframework.http.client.ClientHttpResponse response) {
		int statusCode = 0;
		try {
			statusCode = response.getStatusCode().value();
			ErrorResponse body = objectMapper.readValue(response.getBody(), ErrorResponse.class);
			throw new AiProcessingClientException(
					body.code(),
					body.message(),
					body.retryable(),
					statusCode,
					body.requestId(),
					body.analysisRunId(),
					null);
		} catch (AiProcessingClientException error) {
			throw error;
		} catch (Exception error) {
			throw new AiProcessingClientException(
					"INTERNAL_ERROR",
					"AI Processing returned an invalid error response",
					false,
					statusCode,
					null,
					null,
					error);
		}
	}

	private static AiProcessingClientException transportFailure(
			String code,
			String message,
			RestClientException cause) {
		return new AiProcessingClientException(
				code,
				message,
				false,
				0,
				UUID.randomUUID(),
				null,
				cause);
	}
}
