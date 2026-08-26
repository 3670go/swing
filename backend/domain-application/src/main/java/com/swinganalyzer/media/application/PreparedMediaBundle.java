package com.swinganalyzer.media.application;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class PreparedMediaBundle implements AutoCloseable {

	private static final Logger logger = LoggerFactory.getLogger(PreparedMediaBundle.class);

	private final Path directory;
	private final List<PreparedMedia> media;

	public PreparedMediaBundle(Path directory, List<PreparedMedia> media) {
		this.directory = directory;
		this.media = List.copyOf(media);
	}

	public List<PreparedMedia> media() {
		return media;
	}

	@Override
	public void close() {
		try (var paths = Files.walk(directory)) {
			paths.sorted(Comparator.reverseOrder()).forEach(path -> {
				try {
					Files.deleteIfExists(path);
				} catch (IOException error) {
					logger.warn("Could not delete temporary media path", error);
				}
			});
		} catch (IOException error) {
			logger.warn("Could not walk temporary media directory", error);
		}
	}
}
