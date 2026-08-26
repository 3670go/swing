package com.swinganalyzer.shared.api;

import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

import com.swinganalyzer.shared.error.PublicApiException;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

@Component
public class ShotContextParser {

	private final ObjectMapper objectMapper;
	private final Validator validator;

	public ShotContextParser(ObjectMapper objectMapper, Validator validator) {
		this.objectMapper = objectMapper;
		this.validator = validator;
	}

	public ShotContextRequest parseJson(String contextJson) {
		try {
			return validate(objectMapper.readValue(contextJson, ShotContextRequest.class));
		} catch (JacksonException error) {
			throw invalid();
		}
	}

	public ShotContextRequest parseObject(Object context) {
		try {
			return validate(objectMapper.convertValue(context, ShotContextRequest.class));
		} catch (IllegalArgumentException error) {
			throw invalid();
		}
	}

	private ShotContextRequest validate(ShotContextRequest context) {
		Set<ConstraintViolation<ShotContextRequest>> violations = validator.validate(context);
		if (!violations.isEmpty()) {
			throw invalid();
		}
		return context;
	}

	private static PublicApiException invalid() {
		return new PublicApiException(HttpStatus.valueOf(422), "INVALID_SHOT_CONTEXT");
	}
}
