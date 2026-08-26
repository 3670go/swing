package com.swinganalyzer.media.application;

import java.nio.file.Path;

public record PreparedMedia(
		Path path,
		String contentType,
		String kind,
		String sha256,
		long sizeBytes,
		String suffix) {
}
