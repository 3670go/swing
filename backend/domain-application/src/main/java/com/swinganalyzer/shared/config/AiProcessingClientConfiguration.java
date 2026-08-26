package com.swinganalyzer.shared.config;

import java.net.http.HttpClient;
import java.time.Duration;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.http.converter.json.JacksonJsonHttpMessageConverter;
import org.springframework.web.client.RestClient;

import com.swinganalyzer.analysis.application.AiProcessingClient;
import com.swinganalyzer.analysis.infrastructure.aiclient.RestAiProcessingClient;

import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.json.JsonMapper;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(AiProcessingProperties.class)
@ConditionalOnProperty(prefix = "ai-processing", name = "enabled", havingValue = "true")
public class AiProcessingClientConfiguration {

	@Bean
	AiProcessingClient aiProcessingClient(AiProcessingProperties properties) {
		validate(properties);
		Duration timeout = Duration.ofSeconds(properties.getTimeoutSeconds());
		HttpClient httpClient = HttpClient.newBuilder().connectTimeout(timeout).build();
		JdkClientHttpRequestFactory requestFactory = new JdkClientHttpRequestFactory(httpClient);
		requestFactory.setReadTimeout(timeout);

		JsonMapper objectMapper = JsonMapper.builder()
				.propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
				.build();
		RestClient restClient = RestClient.builder()
				.baseUrl(properties.getBaseUrl().toString())
				.defaultHeader(HttpHeaders.AUTHORIZATION, "Bearer " + properties.getToken())
				.requestFactory(requestFactory)
				.configureMessageConverters(converters -> converters
						.withJsonConverter(new JacksonJsonHttpMessageConverter(objectMapper)))
				.build();
		return new RestAiProcessingClient(restClient, objectMapper);
	}

	private static void validate(AiProcessingProperties properties) {
		if (properties.getBaseUrl() == null) {
			throw new IllegalStateException("AI_PROCESSING_BASE_URL is required");
		}
		if (properties.getToken() == null || properties.getToken().isBlank()) {
			throw new IllegalStateException("INTERNAL_API_TOKEN is required");
		}
		if (properties.getTimeoutSeconds() <= 0) {
			throw new IllegalStateException("AI_PROCESSING_TIMEOUT_SECONDS must be positive");
		}
	}
}
