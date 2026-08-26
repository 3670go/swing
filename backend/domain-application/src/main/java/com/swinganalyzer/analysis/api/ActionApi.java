package com.swinganalyzer.analysis.api;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.swinganalyzer.analysis.application.AnalysisApplicationService;
import com.swinganalyzer.analysis.application.AnalysisApplicationService.AnalysisResult;
import com.swinganalyzer.shared.api.ShotContextParser;
import com.swinganalyzer.shared.api.ShotContextRequest;
import com.swinganalyzer.shared.config.ActionProperties;
import com.swinganalyzer.shared.error.PublicApiException;

import jakarta.servlet.http.HttpServletRequest;

@RestController
@RequestMapping("/v1/actions")
public class ActionApi {

	private final AnalysisApplicationService service;
	private final ActionMediaDownloader downloader;
	private final ActionProperties properties;
	private final ShotContextParser contextParser;

	public ActionApi(
			AnalysisApplicationService service,
			ActionMediaDownloader downloader,
			ActionProperties properties,
			ShotContextParser contextParser) {
		this.service = service;
		this.downloader = downloader;
		this.properties = properties;
		this.contextParser = contextParser;
	}

	@PostMapping("/analyze")
	AnalysisResult analyze(
			@RequestBody Map<String, Object> body,
			@RequestHeader(name = "Authorization", required = false) String authorization) {
		verifyAuthorization(authorization);
		String sessionId = requiredString(body, "session_id");
		String question = optionalString(body, "question");
		UUID conversationId = optionalUuid(body.get("conversation_id"));
		ShotContextRequest context = contextParser.parseObject(body.get("context"));
		List<ActionFileReference> references = parseReferences(body);
		try (DownloadedActionBundle files = downloader.download(references)) {
			return service.analyze(
					files.files(),
					sessionId,
					conversationId,
					context.toInternal(),
					question);
		}
	}

	@GetMapping("/openapi.json")
	Map<String, Object> openApi(HttpServletRequest request) {
		String forwardedHost = request.getHeader("x-forwarded-host");
		String host = forwardedHost == null ? request.getHeader("host") : forwardedHost;
		if (host == null || host.isBlank()) {
			throw new PublicApiException(HttpStatus.BAD_REQUEST, "ACTION_SCHEMA_HOST_MISSING");
		}
		String forwardedProto = request.getHeader("x-forwarded-proto");
		String scheme = forwardedProto == null ? request.getScheme() : forwardedProto;
		String hostname = host.split(":", 2)[0].toLowerCase();
		if ("http".equals(scheme) && !List.of("localhost", "127.0.0.1").contains(hostname)) {
			scheme = "https";
		}
		return actionSchema(scheme + "://" + host);
	}

	private void verifyAuthorization(String authorization) {
		String expected = properties.getApiKey();
		String supplied = authorization != null && authorization.startsWith("Bearer ")
				? authorization.substring(7)
				: "";
		boolean valid = !expected.isBlank() && MessageDigest.isEqual(
				expected.getBytes(StandardCharsets.UTF_8), supplied.getBytes(StandardCharsets.UTF_8));
		if (!valid) {
			throw new PublicApiException(HttpStatus.UNAUTHORIZED, "ACTION_AUTH_FAILED");
		}
	}

	private static List<ActionFileReference> parseReferences(Map<String, Object> body) {
		Object value = body.get("openaiFileIdRefs");
		if (value == null) {
			value = body.get("openai_file_id_refs");
		}
		if (!(value instanceof List<?> items)) {
			throw invalid("ACTION_FILES_INVALID");
		}
		List<ActionFileReference> references = new ArrayList<>();
		for (Object item : items) {
			if (!(item instanceof Map<?, ?> file)) {
				throw invalid("ACTION_FILES_INVALID");
			}
			try {
				references.add(new ActionFileReference(
						(String) file.get("name"),
						(String) file.get("mime_type"),
						URI.create((String) file.get("download_link"))));
			} catch (ClassCastException | IllegalArgumentException error) {
				throw invalid("ACTION_FILES_INVALID");
			}
		}
		return references;
	}

	private static String requiredString(Map<String, Object> body, String key) {
		Object value = body.get(key);
		if (!(value instanceof String text) || text.isBlank()) {
			throw invalid("INVALID_REQUEST");
		}
		return text;
	}

	private static String optionalString(Map<String, Object> body, String key) {
		Object value = body.get(key);
		return value instanceof String text ? text.strip() : "";
	}

	private static UUID optionalUuid(Object value) {
		if (value == null) {
			return null;
		}
		try {
			return UUID.fromString((String) value);
		} catch (ClassCastException | IllegalArgumentException error) {
			throw invalid("INVALID_REQUEST");
		}
	}

	private static PublicApiException invalid(String detail) {
		return new PublicApiException(HttpStatus.valueOf(422), detail);
	}

	private static Map<String, Object> actionSchema(String serverUrl) {
		Map<String, Object> fileSchema = Map.of(
				"type", "object",
				"required", List.of("name", "id", "mime_type", "download_link"),
				"properties", Map.of(
						"name", Map.of("type", "string"),
						"id", Map.of("type", "string"),
						"mime_type", Map.of("type", "string"),
						"download_link", Map.of("type", "string", "format", "uri")));
		Map<String, Object> requestSchema = new LinkedHashMap<>();
		requestSchema.put("type", "object");
		requestSchema.put("required", List.of("session_id", "openaiFileIdRefs", "context"));
		requestSchema.put("properties", Map.of(
				"session_id", Map.of("type", "string"),
				"openaiFileIdRefs", Map.of("type", "array", "items", fileSchema),
				"question", Map.of("type", "string"),
				"context", Map.of("type", "object"),
				"conversation_id", Map.of("type", List.of("string", "null"), "format", "uuid")));
		Map<String, Object> operation = Map.of(
				"operationId", "analyzeSwingFiles",
				"summary", "Analyze attached golf swing media",
				"security", List.of(Map.of("BearerAuth", List.of())),
				"requestBody", Map.of(
						"required", true,
						"content", Map.of("application/json", Map.of("schema", requestSchema))),
				"responses", Map.of("200", Map.of("description", "Completed analysis")));
		return Map.of(
				"openapi", "3.1.0",
				"info", Map.of("title", "Swing Analyzer Action", "version", "1.0.0"),
				"servers", List.of(Map.of("url", serverUrl)),
				"paths", Map.of("/v1/actions/analyze", Map.of("post", operation)),
				"components", Map.of("securitySchemes", Map.of(
						"BearerAuth", Map.of("type", "http", "scheme", "bearer"))));
	}

	public record ActionFileReference(String name, String mimeType, URI downloadLink) {
	}
}
