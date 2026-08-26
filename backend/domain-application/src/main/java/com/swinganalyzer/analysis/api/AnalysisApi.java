package com.swinganalyzer.analysis.api;

import java.util.List;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import com.swinganalyzer.analysis.application.AnalysisApplicationService;
import com.swinganalyzer.analysis.application.AnalysisApplicationService.AnalysisResult;
import com.swinganalyzer.analysis.application.AnalysisApplicationService.HistoryItem;
import com.swinganalyzer.shared.api.ShotContextRequest;
import com.swinganalyzer.shared.api.ShotContextParser;
import com.swinganalyzer.shared.error.PublicApiException;


@RestController
@RequestMapping("/v1")
public class AnalysisApi {

	private final AnalysisApplicationService service;
	private final ShotContextParser contextParser;

	public AnalysisApi(
			AnalysisApplicationService service,
			ShotContextParser contextParser) {
		this.service = service;
		this.contextParser = contextParser;
	}

	@PostMapping(path = "/analyze", consumes = "multipart/form-data")
	AnalysisResult analyze(
			@RequestParam("files") List<MultipartFile> files,
			@RequestParam("anonymous_session_id") String anonymousSessionId,
			@RequestParam("context_json") String contextJson,
			@RequestParam(name = "question", defaultValue = "") String question,
			@RequestParam(name = "conversation_id", required = false) UUID conversationId) {
		validateSession(anonymousSessionId);
		if (question.length() > 4000) {
			throw new PublicApiException(HttpStatus.valueOf(422), "INVALID_REQUEST");
		}
		ShotContextRequest context = contextParser.parseJson(contextJson);
		return service.analyze(
				files,
				anonymousSessionId,
				conversationId,
				context.toInternal(),
				question.strip());
	}

	@GetMapping("/history")
	HistoryResponse history(@RequestParam("anonymous_session_id") String anonymousSessionId) {
		validateSession(anonymousSessionId);
		return new HistoryResponse(service.history(anonymousSessionId));
	}

	@DeleteMapping("/analysis/{runId}")
	ResponseEntity<Void> delete(
			@PathVariable UUID runId,
			@RequestParam("anonymous_session_id") String anonymousSessionId) {
		validateSession(anonymousSessionId);
		service.delete(anonymousSessionId, runId);
		return ResponseEntity.noContent().build();
	}

	private static void validateSession(String anonymousSessionId) {
		if (anonymousSessionId == null
				|| anonymousSessionId.length() < 16
				|| anonymousSessionId.length() > 128) {
			throw new PublicApiException(HttpStatus.valueOf(422), "INVALID_REQUEST");
		}
	}

	public record HistoryResponse(List<HistoryItem> items) {
	}
}
