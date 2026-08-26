package com.swinganalyzer.analysis.application;

import java.util.UUID;

public final class AiProcessingClientException extends RuntimeException {

	private final String code;
	private final boolean retryable;
	private final int statusCode;
	private final UUID requestId;
	private final UUID analysisRunId;

	public AiProcessingClientException(
			String code,
			String message,
			boolean retryable,
			int statusCode,
			UUID requestId,
			UUID analysisRunId,
			Throwable cause) {
		super(message, cause);
		this.code = code;
		this.retryable = retryable;
		this.statusCode = statusCode;
		this.requestId = requestId;
		this.analysisRunId = analysisRunId;
	}

	public String code() {
		return code;
	}

	public boolean retryable() {
		return retryable;
	}

	public int statusCode() {
		return statusCode;
	}

	public UUID requestId() {
		return requestId;
	}

	public UUID analysisRunId() {
		return analysisRunId;
	}
}
