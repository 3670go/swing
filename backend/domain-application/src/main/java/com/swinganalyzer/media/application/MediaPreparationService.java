package com.swinganalyzer.media.application;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import com.swinganalyzer.shared.config.MediaProperties;

@Service
public class MediaPreparationService {

	private static final Map<String, MediaType> MEDIA_TYPES = Map.of(
			"image/jpeg", new MediaType("photo", ".jpg"),
			"image/png", new MediaType("photo", ".png"),
			"image/webp", new MediaType("photo", ".webp"),
			"video/mp4", new MediaType("video", ".mp4"),
			"video/quicktime", new MediaType("video", ".mov"),
			"video/webm", new MediaType("video", ".webm"));

	private final MediaProperties properties;

	public MediaPreparationService(MediaProperties properties) {
		this.properties = properties;
	}

	public PreparedMediaBundle prepare(List<MultipartFile> files) {
		if (files == null || files.isEmpty()) {
			throw new MediaStorageException("MEDIA_EMPTY");
		}
		if (files.size() > 10) {
			throw new MediaStorageException("TOO_MANY_MEDIA_FILES");
		}

		try {
			Path directory = Files.createTempDirectory("swing-analysis-");
			List<PreparedMedia> prepared = new ArrayList<>();
			try {
				for (int index = 0; index < files.size(); index++) {
					prepared.add(prepareOne(files.get(index), directory, index + 1));
				}
				return new PreparedMediaBundle(directory, prepared);
			} catch (RuntimeException error) {
				new PreparedMediaBundle(directory, prepared).close();
				throw error;
			}
		} catch (IOException error) {
			throw new MediaStorageException("MEDIA_PREPARATION_FAILED", error);
		}
	}

	private PreparedMedia prepareOne(MultipartFile file, Path directory, int index) {
		String contentType = file.getContentType() == null ? "" : file.getContentType().toLowerCase();
		MediaType mediaType = MEDIA_TYPES.get(contentType);
		if (mediaType == null) {
			throw new MediaStorageException("MEDIA_TYPE_UNSUPPORTED");
		}
		Path target = directory.resolve("original_%02d%s".formatted(index, mediaType.suffix()));
		try {
			MessageDigest digest = MessageDigest.getInstance("SHA-256");
			long size = copyAndHash(file, target, digest, mediaType.kind());
			return new PreparedMedia(
					target,
					contentType,
					mediaType.kind(),
					HexFormat.of().formatHex(digest.digest()),
					size,
					mediaType.suffix());
		} catch (IOException error) {
			throw new MediaStorageException("MEDIA_PREPARATION_FAILED", error);
		} catch (NoSuchAlgorithmException error) {
			throw new IllegalStateException("SHA-256 is unavailable", error);
		}
	}

	private long copyAndHash(
			MultipartFile file,
			Path target,
			MessageDigest digest,
			String kind) throws IOException {
		long size = 0;
		try (InputStream input = file.getInputStream(); OutputStream output = Files.newOutputStream(target)) {
			byte[] buffer = new byte[1024 * 1024];
			int read;
			while ((read = input.read(buffer)) != -1) {
				size += read;
				if ("video".equals(kind) && properties.getMaxVideoBytes() > 0
						&& size > properties.getMaxVideoBytes()) {
					throw new MediaStorageException("VIDEO_TOO_LARGE");
				}
				digest.update(buffer, 0, read);
				output.write(buffer, 0, read);
			}
		}
		if (size == 0) {
			throw new MediaStorageException("MEDIA_EMPTY");
		}
		return size;
	}

	private record MediaType(String kind, String suffix) {
	}
}
