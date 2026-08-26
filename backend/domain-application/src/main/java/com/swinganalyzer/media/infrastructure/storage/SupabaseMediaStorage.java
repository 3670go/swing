package com.swinganalyzer.media.infrastructure.storage;

import java.net.URI;
import java.util.List;
import java.util.Map;

import org.springframework.core.io.FileSystemResource;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import com.swinganalyzer.media.application.MediaStorage;
import com.swinganalyzer.media.application.MediaStorageException;
import com.swinganalyzer.media.application.PreparedMedia;
import com.swinganalyzer.shared.config.MediaProperties;
import com.swinganalyzer.shared.config.SupabaseProperties;


@Component
public class SupabaseMediaStorage implements MediaStorage {

	private static final Logger logger = LoggerFactory.getLogger(SupabaseMediaStorage.class);

	private final SupabaseProperties properties;
	private final MediaProperties mediaProperties;

	public SupabaseMediaStorage(SupabaseProperties properties, MediaProperties mediaProperties) {
		this.properties = properties;
		this.mediaProperties = mediaProperties;
	}

	@Override
	public void upload(String objectPath, PreparedMedia media) {
		try {
			client().post()
					.uri(uriBuilder -> appendObjectPath(
							uriBuilder.pathSegment("object", properties.getStorageBucket()), objectPath).build())
					.contentType(MediaType.parseMediaType(media.contentType()))
					.header("x-upsert", "false")
					.header(HttpHeaders.CACHE_CONTROL, "3600")
					.body(new FileSystemResource(media.path()))
					.retrieve()
					.toBodilessEntity();
		} catch (RestClientException error) {
			logger.error("Supabase Storage upload failed: {}", error.getMessage());
			throw new MediaStorageException("STORAGE_UNAVAILABLE", error);
		}
	}

	@Override
	public URI createSignedReadUrl(String objectPath) {
		try {
			Map<?, ?> response = client().post()
					.uri(uriBuilder -> appendObjectPath(
							uriBuilder.pathSegment("object", "sign", properties.getStorageBucket()),
							objectPath).build())
					.contentType(MediaType.APPLICATION_JSON)
					.body(new SignedUrlRequest(mediaProperties.getSignedReadTtlSeconds()))
					.retrieve()
					.body(Map.class);
			String signedPath = response == null ? null : (String) response.get("signedURL");
			if (signedPath == null || signedPath.isBlank()) {
				throw new MediaStorageException("STORAGE_SIGNING_FAILED");
			}
			String base = properties.getUrl().toString().replaceAll("/+$", "");
			if (signedPath.startsWith("/storage/v1/")) {
				return URI.create(base + signedPath);
			}
			return URI.create(base + "/storage/v1" + (signedPath.startsWith("/") ? "" : "/") + signedPath);
		} catch (RestClientException error) {
			logger.error("Supabase signed URL request failed: {}", error.getMessage());
			throw new MediaStorageException("STORAGE_UNAVAILABLE", error);
		}
	}

	@Override
	public void deleteMany(List<String> objectPaths) {
		if (objectPaths.isEmpty()) {
			return;
		}
		try {
			client().method(HttpMethod.DELETE)
					.uri(uriBuilder -> uriBuilder.pathSegment("object", properties.getStorageBucket()).build())
					.body(new DeleteRequest(objectPaths))
					.retrieve()
					.toBodilessEntity();
		} catch (RestClientException error) {
			logger.error("Supabase Storage deletion failed: {}", error.getMessage());
			throw new MediaStorageException("STORAGE_UNAVAILABLE", error);
		}
	}

	private RestClient client() {
		validateConfiguration();
		return RestClient.builder()
				.baseUrl(properties.getUrl().toString().replaceAll("/+$", "") + "/storage/v1")
				.defaultHeader("apikey", properties.getSecretKey())
				.defaultHeader(HttpHeaders.AUTHORIZATION, "Bearer " + properties.getSecretKey())
				.build();
	}

	private void validateConfiguration() {
		if (properties.getUrl() == null || properties.getSecretKey().isBlank()) {
			throw new MediaStorageException("STORAGE_NOT_CONFIGURED");
		}
		if (mediaProperties.getSignedReadTtlSeconds() <= 0) {
			throw new MediaStorageException("SIGNED_READ_TTL_INVALID");
		}
	}

	private static org.springframework.web.util.UriBuilder appendObjectPath(
			org.springframework.web.util.UriBuilder builder,
			String objectPath) {
		for (String segment : objectPath.split("/")) {
			builder.pathSegment(segment);
		}
		return builder;
	}

	private record SignedUrlRequest(int expiresIn) {
	}

	private record DeleteRequest(List<String> prefixes) {
	}
}
