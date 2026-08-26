package com.swinganalyzer.media.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.charset.StandardCharsets;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;

import com.swinganalyzer.shared.config.MediaProperties;

class MediaPreparationServiceTests {

	@Test
	void hashesAndClassifiesSupportedMedia() {
		MediaPreparationService service = new MediaPreparationService(new MediaProperties());
		MockMultipartFile photo = new MockMultipartFile(
				"files", "swing.png", "image/png", "image-data".getBytes(StandardCharsets.UTF_8));

		try (PreparedMediaBundle bundle = service.prepare(List.of(photo))) {
			assertThat(bundle.media()).singleElement().satisfies(media -> {
				assertThat(media.kind()).isEqualTo("photo");
				assertThat(media.contentType()).isEqualTo("image/png");
				assertThat(media.sha256()).hasSize(64);
			});
		}
	}

	@Test
	void rejectsUnsupportedMediaBeforeStorageCall() {
		MediaPreparationService service = new MediaPreparationService(new MediaProperties());
		MockMultipartFile text = new MockMultipartFile(
				"files", "notes.txt", "text/plain", "not-media".getBytes(StandardCharsets.UTF_8));

		assertThatThrownBy(() -> service.prepare(List.of(text)))
				.isInstanceOf(MediaStorageException.class)
				.hasMessage("MEDIA_TYPE_UNSUPPORTED");
	}
}
