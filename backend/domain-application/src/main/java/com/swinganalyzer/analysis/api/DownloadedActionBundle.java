package com.swinganalyzer.analysis.api;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.multipart.MultipartFile;

final class DownloadedActionBundle implements AutoCloseable {

	private static final Logger logger = LoggerFactory.getLogger(DownloadedActionBundle.class);

	private final Path directory;
	private final List<MultipartFile> files;

	DownloadedActionBundle(Path directory, List<MultipartFile> files) {
		this.directory = directory;
		this.files = List.copyOf(files);
	}

	List<MultipartFile> files() {
		return files;
	}

	@Override
	public void close() {
		try (var paths = Files.walk(directory)) {
			paths.sorted(Comparator.reverseOrder()).forEach(path -> {
				try {
					Files.deleteIfExists(path);
				} catch (IOException error) {
					logger.warn("Could not delete downloaded Action file", error);
				}
			});
		} catch (IOException error) {
			logger.warn("Could not walk downloaded Action directory", error);
		}
	}

	static final class PathMultipartFile implements MultipartFile {

		private final Path path;
		private final String name;
		private final String originalFilename;
		private final String contentType;

		PathMultipartFile(Path path, String name, String originalFilename, String contentType) {
			this.path = path;
			this.name = name;
			this.originalFilename = originalFilename;
			this.contentType = contentType;
		}

		@Override
		public String getName() {
			return name;
		}

		@Override
		public String getOriginalFilename() {
			return originalFilename;
		}

		@Override
		public String getContentType() {
			return contentType;
		}

		@Override
		public boolean isEmpty() {
			return getSize() == 0;
		}

		@Override
		public long getSize() {
			try {
				return Files.size(path);
			} catch (IOException error) {
				throw new IllegalStateException("Downloaded Action file is unavailable", error);
			}
		}

		@Override
		public byte[] getBytes() throws IOException {
			return Files.readAllBytes(path);
		}

		@Override
		public InputStream getInputStream() throws IOException {
			return Files.newInputStream(path);
		}

		@Override
		public void transferTo(java.io.File destination) throws IOException {
			Files.copy(path, destination.toPath());
		}

		@Override
		public void transferTo(Path destination) throws IOException {
			Files.copy(path, destination);
		}
	}
}
