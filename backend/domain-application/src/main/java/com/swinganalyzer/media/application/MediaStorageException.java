package com.swinganalyzer.media.application;

public final class MediaStorageException extends RuntimeException {

	private final String code;

	public MediaStorageException(String code, Throwable cause) {
		super(code, cause);
		this.code = code;
	}

	public MediaStorageException(String code) {
		super(code);
		this.code = code;
	}

	public String code() {
		return code;
	}
}
