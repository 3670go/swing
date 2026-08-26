package com.swinganalyzer.analysis.application.model;

import java.net.URI;
import java.util.List;
import java.util.UUID;

public final class AiProcessingContract {

	private AiProcessingContract() {
	}

	public record ShotContext(
			String shotProfile,
			String club,
			String cameraView,
			String handedness,
			String analysisGoal,
			String shortGameType,
			String videoType,
			String shotResult) {
	}

	public record InteractionMeta(
			String responseMode,
			String positiveTopic,
			String questionTopic,
			String inviteMode) {
	}

	public record HistoryMessage(String role, String content, InteractionMeta interactionMeta) {
	}

	public record MediaReference(
			UUID mediaId,
			String kind,
			String contentType,
			long sizeBytes,
			String sha256,
			URI readUrl) {
	}

	public record AnalysisRequest(
			UUID requestId,
			UUID analysisRunId,
			List<MediaReference> media,
			ShotContext shotContext,
			String userQuestion,
			String userFeel,
			List<HistoryMessage> history) {
	}

	public record ObservationItem(
			String timestamp,
			String subject,
			String reference,
			String phase,
			String state,
			String assessmentCategory,
			double confidence) {
	}

	public record VisionObservation(
			boolean isGolfMedia,
			String golfMediaReason,
			List<ObservationItem> observations,
			List<String> cannotDetermine) {
	}

	public record AssessmentFinding(
			String category,
			List<Integer> observationIndexes,
			String summary,
			double confidence) {
	}

	public record BaseAssessment(
			String primaryCategory,
			String importance,
			List<AssessmentFinding> findings,
			List<String> cannotDetermine,
			String assessmentHash) {
	}

	public record CoachContent(
			String evidenceMode,
			String directAnswer,
			List<String> causalChain,
			String evidenceBoundary,
			List<String> cannotDetermine,
			List<Integer> observationIndexes,
			String baseAssessmentHash,
			String singleChange,
			String verification,
			String preserveCandidate,
			String preserveTopic,
			String followUpInformationNeeded) {
	}

	public record AnalysisResponse(
			UUID requestId,
			UUID analysisRunId,
			String status,
			VisionObservation observation,
			BaseAssessment baseAssessment,
			CoachContent coachContent) {
	}

	public record TextCoachingRequest(
			UUID requestId,
			String message,
			ShotContext shotContext,
			List<HistoryMessage> history,
			boolean hasLatestAnalysis) {
	}

	public record TextCoachingResponse(UUID requestId, CoachContent coachContent) {
	}

	public record HealthResponse(String service, String status, boolean modelConfigured) {
	}

	public record ErrorResponse(
			String code,
			String message,
			boolean retryable,
			UUID requestId,
			UUID analysisRunId) {
	}
}
