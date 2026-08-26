package com.swinganalyzer.shared.error;

import org.springframework.http.HttpStatus;

public final class PublicApiException extends RuntimeException {

	private final HttpStatus status;
	private final String detail;

	public PublicApiException(HttpStatus status, String detail) {
		super(detail);
		this.status = status;
		this.detail = detail;
	}

	public HttpStatus status() {
		return status;
	}

	public String detail() {
		return detail;
	}
}
