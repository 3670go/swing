package com.swinganalyzer.shared.error;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

@RestControllerAdvice
public class PublicApiExceptionHandler {

	@ExceptionHandler(PublicApiException.class)
	ResponseEntity<Map<String, String>> handlePublicApi(PublicApiException error) {
		return ResponseEntity.status(error.status()).body(Map.of("detail", error.detail()));
	}

	@ExceptionHandler(MethodArgumentNotValidException.class)
	ResponseEntity<Map<String, String>> handleValidation() {
		return ResponseEntity.status(422).body(Map.of("detail", "INVALID_REQUEST"));
	}

	@ExceptionHandler(MaxUploadSizeExceededException.class)
	ResponseEntity<Map<String, String>> handleUploadLimit() {
		return ResponseEntity.status(413).body(Map.of("detail", "MEDIA_TOO_LARGE"));
	}
}
