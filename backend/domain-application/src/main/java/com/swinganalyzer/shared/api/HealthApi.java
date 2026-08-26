package com.swinganalyzer.shared.api;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import com.swinganalyzer.analysis.application.AiProcessingClient;
import com.swinganalyzer.analysis.application.AiProcessingClientException;
import com.swinganalyzer.shared.config.SupabaseProperties;

@RestController
public class HealthApi {

	private final JdbcTemplate jdbcTemplate;
	private final SupabaseProperties supabaseProperties;
	private final ObjectProvider<AiProcessingClient> aiClientProvider;

	public HealthApi(
			JdbcTemplate jdbcTemplate,
			SupabaseProperties supabaseProperties,
			ObjectProvider<AiProcessingClient> aiClientProvider) {
		this.jdbcTemplate = jdbcTemplate;
		this.supabaseProperties = supabaseProperties;
		this.aiClientProvider = aiClientProvider;
	}

	@GetMapping("/health")
	Map<String, Object> health() {
		Map<String, Object> response = new LinkedHashMap<>();
		response.put("status", "ok");
		response.put("database_configured", databaseReady());
		response.put("storage_configured", storageConfigured());
		response.put("model_configured", modelConfigured());
		response.put("model", "ai-processing");
		return response;
	}

	private boolean databaseReady() {
		try {
			return Integer.valueOf(1).equals(jdbcTemplate.queryForObject("SELECT 1", Integer.class));
		} catch (DataAccessException error) {
			return false;
		}
	}

	private boolean storageConfigured() {
		return supabaseProperties.getUrl() != null && !supabaseProperties.getSecretKey().isBlank();
	}

	private boolean modelConfigured() {
		AiProcessingClient client = aiClientProvider.getIfAvailable();
		if (client == null) {
			return false;
		}
		try {
			return client.health().modelConfigured();
		} catch (AiProcessingClientException error) {
			return false;
		}
	}
}
