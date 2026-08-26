package com.swinganalyzer.analysis.api;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;

import com.swinganalyzer.analysis.api.ActionApi.ActionFileReference;
import com.swinganalyzer.analysis.api.DownloadedActionBundle.PathMultipartFile;
import com.swinganalyzer.shared.config.ActionProperties;
import com.swinganalyzer.shared.config.MediaProperties;
import com.swinganalyzer.shared.error.PublicApiException;

@Component
class ActionMediaDownloader {

	private final ActionProperties actionProperties;
	private final MediaProperties mediaProperties;
	private final HttpClient httpClient;

	ActionMediaDownloader(ActionProperties actionProperties, MediaProperties mediaProperties) {
		this.actionProperties = actionProperties;
		this.mediaProperties = mediaProperties;
		this.httpClient = HttpClient.newBuilder()
				.connectTimeout(Duration.ofSeconds(20))
				.followRedirects(HttpClient.Redirect.NEVER)
				.build();
	}

	DownloadedActionBundle download(List<ActionFileReference> references) {
		if (references.isEmpty() || references.size() > 10) {
			throw invalid("ACTION_FILES_INVALID");
		}
		try {
			Path directory = Files.createTempDirectory("gpt-action-");
			List<MultipartFile> files = new ArrayList<>();
			try {
				for (int index = 0; index < references.size(); index++) {
					ActionFileReference reference = references.get(index);
					validateUrl(reference.downloadLink());
					Path target = directory.resolve("action_%02d.bin".formatted(index + 1));
					downloadOne(reference, target);
					files.add(new PathMultipartFile(
							target, "files", reference.name(), reference.mimeType()));
				}
				return new DownloadedActionBundle(directory, files);
			} catch (RuntimeException error) {
				new DownloadedActionBundle(directory, files).close();
				throw error;
			}
		} catch (IOException error) {
			throw new PublicApiException(HttpStatus.BAD_GATEWAY, "ACTION_FILE_DOWNLOAD_FAILED");
		}
	}

	private void downloadOne(ActionFileReference reference, Path target) {
		try {
			HttpRequest request = HttpRequest.newBuilder(reference.downloadLink())
					.timeout(Duration.ofMinutes(2))
					.GET()
					.build();
			HttpResponse<Path> response = httpClient.send(
					request, HttpResponse.BodyHandlers.ofFile(target));
			if (response.statusCode() < 200 || response.statusCode() >= 300) {
				throw new PublicApiException(HttpStatus.BAD_GATEWAY, "ACTION_FILE_DOWNLOAD_FAILED");
			}
			long size = Files.size(target);
			if (size == 0) {
				throw invalid("MEDIA_EMPTY");
			}
			if (reference.mimeType().startsWith("video/")
					&& mediaProperties.getMaxVideoBytes() > 0
					&& size > mediaProperties.getMaxVideoBytes()) {
				throw invalid("VIDEO_TOO_LARGE");
			}
		} catch (IOException error) {
			throw new PublicApiException(HttpStatus.BAD_GATEWAY, "ACTION_FILE_DOWNLOAD_FAILED");
		} catch (InterruptedException error) {
			Thread.currentThread().interrupt();
			throw new PublicApiException(HttpStatus.BAD_GATEWAY, "ACTION_FILE_DOWNLOAD_INTERRUPTED");
		}
	}

	private void validateUrl(URI uri) {
		String host = uri.getHost() == null ? "" : uri.getHost().toLowerCase();
		if (!"https".equalsIgnoreCase(uri.getScheme())
				|| uri.getUserInfo() != null
				|| (uri.getPort() != -1 && uri.getPort() != 443)
				|| !actionProperties.getFileHosts().contains(host)) {
			throw invalid("ACTION_FILE_HOST_NOT_ALLOWED");
		}
	}

	private static PublicApiException invalid(String detail) {
		return new PublicApiException(HttpStatus.valueOf(422), detail);
	}
}
