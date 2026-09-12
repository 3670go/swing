package com.swinganalyzer.analysis.application.model;

import java.net.URI;
import java.util.List;
import java.util.UUID;

/**
 * Java transport records for the frozen internal AI API contract
 * ({@code contracts/internal-api.openapi.yaml} version 2.2.0).
 *
 * <p>Field names map to the snake_case JSON contract through the SNAKE_CASE
 * {@code ObjectMapper} configured for the internal HTTP client. These records
 * define the wire shape only; product state application belongs to Java use
 * cases, not to this contract.
 */
public final class AiProcessingContract {

	private AiProcessingContract() {
	}

	// --- Shared value objects -------------------------------------------------

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

	public record CoachingScope(
			String shotProfile,
			String club,
			String clubGroup,
			String shortGameType) {
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

	public record EvidenceReference(String sourceType, String sourceId) {
	}

	// --- Context Packet (Java -> Python input) --------------------------------

	public record RequestContext(
			String userMessage,
			String userFeel,
			ShotContext selectedShotContext,
			boolean mediaPresence) {
	}

	public record ActiveCoachingTopic(
			UUID topicId,
			int version,
			String userProblem,
			String rootProblem,
			CoachingScope scope,
			String activeHypothesis,
			String currentExperiment,
			String carryForwardFeel) {
	}

	public record RoadmapMilestoneSummary(
			UUID milestoneId,
			int version,
			String title,
			String evidenceLevel,
			String completionCondition) {
	}

	public record RoadmapContext(
			UUID roadmapId,
			int version,
			String targetSwing,
			RoadmapMilestoneSummary currentMilestone,
			List<RoadmapMilestoneSummary> completedMilestones,
			String nextCompletionCondition) {
	}

	public record AnalysisEpisodeSummary(
			UUID episodeId,
			String observationSummary,
			String evidenceLevel,
			String capturedAt,
			CoachingScope scope) {
	}

	public record UserContextFact(
			UUID factId,
			int version,
			String statement,
			String evidenceLevel,
			CoachingScope scope,
			List<UUID> sourceEpisodeIds,
			String factType,
			String bodyRegion,
			String expiresAt) {

		public UserContextFact(
				UUID factId,
				int version,
				String statement,
				String evidenceLevel,
				CoachingScope scope,
				List<UUID> sourceEpisodeIds) {
			this(factId, version, statement, evidenceLevel, scope, sourceEpisodeIds, null, null, null);
		}
	}

	public record PendingOpenLoop(
			UUID openLoopId,
			int version,
			String state,
			String carryForwardFeel,
			String nextSingleChange,
			String nextVerification,
			String predictedResult) {
	}

	public record ProgressEventSummary(
			UUID progressEventId,
			UUID topicId,
			UUID milestoneId,
			String progressLevel,
			String userSignal) {
	}

	public record RecognizedTopicSummary(
			UUID topicId,
			int milestoneVersion,
			String recognizedAt) {
	}

	public record RecognitionContext(
			List<ProgressEventSummary> unrecognizedProgressEvents,
			List<RecognizedTopicSummary> recentlyRecognizedTopics,
			String lastRoadmapRevealAt) {
	}

	public record ContextPacket(
			UUID contextSnapshotId,
			int contextSnapshotVersion,
			RequestContext requestContext,
			ActiveCoachingTopic activeCoachingTopic,
			RoadmapContext roadmapContext,
			List<HistoryMessage> recentDialogue,
			List<AnalysisEpisodeSummary> relevantAnalysisEpisodes,
			List<UserContextFact> relevantUserContextFacts,
			PendingOpenLoop pendingOpenLoop,
			RecognitionContext recognitionContext) {
	}

	// --- Analysis observation / assessment ------------------------------------

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

	// --- Coaching Turn Plan (Python -> Java output) ---------------------------

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

	public record ProblemReframeCandidate(
			String previousProblem,
			String proposedRootProblem,
			String causalExplanation,
			List<EvidenceReference> evidenceReferences) {
	}

	public record CoachingTopicCandidate(
			String action,
			UUID targetTopicId,
			Integer expectedVersion,
			CoachingScope scope,
			String title) {
	}

	public record UserContextFactCandidate(
			String action,
			String factType,
			String bodyRegion,
			String statement,
			CoachingScope scope) {
	}

	public record RoadmapUpdateCandidate(
			String targetType,
			UUID targetId,
			Integer expectedVersion,
			String proposedTransition,
			String proposedContent,
			List<EvidenceReference> evidenceReferences) {
	}

	public record ProgressCandidate(
			UUID targetMilestoneId,
			int expectedVersion,
			String progressLevel,
			String userSignal,
			List<EvidenceReference> evidenceReferences) {
	}

	public record RecognitionCandidate(
			String target,
			String proposedIntensity,
			String recognitionContent) {
	}

	public record OpenLoopCandidate(
			String carryForwardFeel,
			String nextSingleChange,
			String nextVerification,
			String completionCondition,
			String predictedResult,
			String question) {
	}

	public record CoachingTurnPlan(
			CoachContent coachContent,
			ProblemReframeCandidate problemReframeCandidate,
			CoachingTopicCandidate coachingTopicCandidate,
			List<UserContextFactCandidate> userContextFactCandidates,
			List<RoadmapUpdateCandidate> roadmapUpdateCandidates,
			ProgressCandidate progressCandidate,
			RecognitionCandidate recognitionCandidate,
			OpenLoopCandidate openLoopCandidate) {

		public CoachingTurnPlan(
				CoachContent coachContent,
				ProblemReframeCandidate problemReframeCandidate,
				CoachingTopicCandidate coachingTopicCandidate,
				List<RoadmapUpdateCandidate> roadmapUpdateCandidates,
				ProgressCandidate progressCandidate,
				RecognitionCandidate recognitionCandidate,
				OpenLoopCandidate openLoopCandidate) {
			this(
					coachContent,
					problemReframeCandidate,
					coachingTopicCandidate,
					List.of(),
					roadmapUpdateCandidates,
					progressCandidate,
					recognitionCandidate,
					openLoopCandidate);
		}
	}

	// --- Internal API request/response envelopes ------------------------------

	public record InternalAnalysisRequest(
			UUID requestId,
			UUID analysisRunId,
			List<MediaReference> media,
			ContextPacket contextPacket) {
	}

	public record InternalAnalysisResponse(
			UUID requestId,
			UUID analysisRunId,
			String status,
			VisionObservation observation,
			BaseAssessment baseAssessment,
			CoachingTurnPlan coachingTurnPlan) {
	}

	public record InternalTextCoachingRequest(
			UUID requestId,
			ContextPacket contextPacket) {
	}

	public record InternalTextCoachingResponse(
			UUID requestId,
			CoachingTurnPlan coachingTurnPlan) {
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
