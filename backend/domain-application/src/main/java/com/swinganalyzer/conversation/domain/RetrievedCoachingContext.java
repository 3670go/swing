package com.swinganalyzer.conversation.domain;

import java.util.List;
import java.util.UUID;

/**
 * Minimal domain read model for the coaching state that a single request may
 * carry into an AI call. It holds only the state selected for the current
 * request scope; the mapping to the transport {@code ContextPacket} lives in the
 * application layer.
 *
 * <p>Session 2 scope: read-only selection. Applying Coaching Turn Plan
 * candidates and state transitions is Session 3.
 */
public record RetrievedCoachingContext(
		ActiveTopic activeTopic,
		Roadmap roadmap,
		List<Fact> facts,
		OpenLoop pendingOpenLoop,
		Recognition recognition) {

	public RetrievedCoachingContext {
		facts = facts == null ? List.of() : List.copyOf(facts);
		recognition = recognition == null ? Recognition.empty() : recognition;
	}

	public static RetrievedCoachingContext empty() {
		return new RetrievedCoachingContext(null, null, List.of(), null, Recognition.empty());
	}

	/**
	 * The shot/coaching scope of a topic or fact. {@link #matches(CoachingScope)}
	 * decides whether this scope is compatible with a request scope. A {@code null}
	 * field on either side is treated as "unspecified" and never forces a mismatch;
	 * two specified but different values block.
	 */
	public record CoachingScope(String shotProfile, String club, String clubGroup, String shortGameType) {

		public boolean matches(CoachingScope request) {
			if (request == null) {
				return false;
			}
			return compatible(shotProfile, request.shotProfile)
					&& compatible(shortGameType, request.shortGameType)
					&& compatible(club, request.club)
					&& compatible(clubGroup, request.clubGroup);
		}

		private static boolean compatible(String left, String right) {
			return left == null || right == null || left.equals(right);
		}
	}

	public record ActiveTopic(
			UUID topicId,
			int version,
			String userProblem,
			String rootProblem,
			CoachingScope scope,
			String activeHypothesis,
			String currentExperiment,
			String carryForwardFeel) {
	}

	public record Milestone(
			UUID milestoneId,
			int version,
			String title,
			String evidenceLevel,
			String completionCondition) {
	}

	public record Roadmap(
			UUID roadmapId,
			int version,
			String targetSwing,
			Milestone currentMilestone,
			List<Milestone> completedMilestones,
			String nextCompletionCondition) {

		public Roadmap {
			completedMilestones = completedMilestones == null ? List.of() : List.copyOf(completedMilestones);
		}
	}

	public record Fact(
			UUID factId,
			int version,
			String statement,
			String evidenceLevel,
			CoachingScope scope,
			List<UUID> sourceEpisodeIds,
			String factType,
			String bodyRegion,
			String expiresAt) {

		public Fact {
			sourceEpisodeIds = sourceEpisodeIds == null ? List.of() : List.copyOf(sourceEpisodeIds);
		}
	}

	public record OpenLoop(
			UUID openLoopId,
			int version,
			String carryForwardFeel,
			String nextSingleChange,
			String nextVerification,
			String predictedResult) {
	}

	public record ProgressEvent(
			UUID progressEventId,
			UUID topicId,
			UUID milestoneId,
			String progressLevel,
			String userSignal) {
	}

	public record RecognizedTopic(
			UUID topicId,
			Integer milestoneVersion,
			String recognizedAt) {
	}

	public record Recognition(
			List<ProgressEvent> unrecognizedProgressEvents,
			List<RecognizedTopic> recentlyRecognizedTopics,
			String lastRoadmapRevealAt) {

		public Recognition {
			unrecognizedProgressEvents = unrecognizedProgressEvents == null
					? List.of() : List.copyOf(unrecognizedProgressEvents);
			recentlyRecognizedTopics = recentlyRecognizedTopics == null
					? List.of() : List.copyOf(recentlyRecognizedTopics);
		}

		public static Recognition empty() {
			return new Recognition(List.of(), List.of(), null);
		}
	}
}
