package com.swinganalyzer.conversation.application;

import java.util.List;

import org.springframework.stereotype.Component;

import com.swinganalyzer.analysis.application.model.AiProcessingContract.ActiveCoachingTopic;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.ContextPacket;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.PendingOpenLoop;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.ProgressEventSummary;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.RecognitionContext;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.RecognizedTopicSummary;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.RequestContext;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.RoadmapContext;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.RoadmapMilestoneSummary;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.ShotContext;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.Fact;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.Milestone;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.ProgressEvent;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.RecognizedTopic;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.Roadmap;

/**
 * Maps a {@link ContextSelection} (DB-backed coaching state + recent dialogue)
 * into the frozen 2.0.0 transport {@code ContextPacket}.
 *
 * <p>The recent dialogue is already deduplicated and capped by
 * {@link ContextRetrievalService}. Analysis episodes have no V5 table and are left
 * empty in Session 2. The snapshot id is supplied by the caller so the packet's
 * {@code context_snapshot_id} equals the persisted {@code context_snapshots.id}.
 */
@Component
public class ContextPacketAssembler {

	public ContextPacket assemble(
			java.util.UUID snapshotId,
			String userMessage,
			ShotContext shotContext,
			boolean mediaPresence,
			ContextSelection selection) {
		RetrievedCoachingContext coaching = selection.coachingContext();
		RequestContext requestContext = new RequestContext(
				userMessage, null, shotContext, mediaPresence);
		return new ContextPacket(
				snapshotId,
				1,
				requestContext,
				toActiveTopic(coaching),
				toRoadmapContext(coaching.roadmap()),
				selection.recentDialogue(),
				List.of(),
				toFacts(coaching.facts()),
				toPendingOpenLoop(coaching),
				toRecognitionContext(coaching.recognition()));
	}

	private static com.swinganalyzer.analysis.application.model.AiProcessingContract.CoachingScope toScope(
			RetrievedCoachingContext.CoachingScope scope) {
		if (scope == null) {
			return null;
		}
		return new com.swinganalyzer.analysis.application.model.AiProcessingContract.CoachingScope(
				scope.shotProfile(), scope.club(), scope.clubGroup(), scope.shortGameType());
	}

	private static ActiveCoachingTopic toActiveTopic(RetrievedCoachingContext coaching) {
		var topic = coaching.activeTopic();
		if (topic == null) {
			return null;
		}
		return new ActiveCoachingTopic(
				topic.topicId(),
				topic.version(),
				topic.userProblem(),
				topic.rootProblem(),
				toScope(topic.scope()),
				topic.activeHypothesis(),
				topic.currentExperiment(),
				topic.carryForwardFeel());
	}

	private static RoadmapContext toRoadmapContext(Roadmap roadmap) {
		if (roadmap == null) {
			return null;
		}
		return new RoadmapContext(
				roadmap.roadmapId(),
				roadmap.version(),
				roadmap.targetSwing(),
				toMilestoneSummary(roadmap.currentMilestone()),
				roadmap.completedMilestones().stream()
						.map(ContextPacketAssembler::toMilestoneSummary)
						.toList(),
				roadmap.nextCompletionCondition());
	}

	private static RoadmapMilestoneSummary toMilestoneSummary(Milestone milestone) {
		if (milestone == null) {
			return null;
		}
		return new RoadmapMilestoneSummary(
				milestone.milestoneId(),
				milestone.version(),
				milestone.title(),
				milestone.evidenceLevel(),
				milestone.completionCondition());
	}

	private static List<com.swinganalyzer.analysis.application.model.AiProcessingContract.UserContextFact> toFacts(
			List<Fact> facts) {
		return facts.stream()
				.map(fact -> new com.swinganalyzer.analysis.application.model.AiProcessingContract.UserContextFact(
						fact.factId(),
						fact.version(),
						fact.statement(),
						fact.evidenceLevel(),
						toScope(fact.scope()),
						fact.sourceEpisodeIds()))
				.toList();
	}

	private static PendingOpenLoop toPendingOpenLoop(RetrievedCoachingContext coaching) {
		var openLoop = coaching.pendingOpenLoop();
		if (openLoop == null) {
			return null;
		}
		return new PendingOpenLoop(
				openLoop.openLoopId(),
				openLoop.version(),
				"PENDING",
				openLoop.carryForwardFeel(),
				openLoop.nextSingleChange(),
				openLoop.nextVerification(),
				openLoop.predictedResult());
	}

	private static RecognitionContext toRecognitionContext(RetrievedCoachingContext.Recognition recognition) {
		List<ProgressEventSummary> unrecognized = recognition.unrecognizedProgressEvents().stream()
				.map(ContextPacketAssembler::toProgressEventSummary)
				.toList();
		List<RecognizedTopicSummary> recognized = recognition.recentlyRecognizedTopics().stream()
				.filter(topic -> topic.milestoneVersion() != null)
				.map(ContextPacketAssembler::toRecognizedTopicSummary)
				.toList();
		return new RecognitionContext(unrecognized, recognized, recognition.lastRoadmapRevealAt());
	}

	private static ProgressEventSummary toProgressEventSummary(ProgressEvent event) {
		return new ProgressEventSummary(
				event.progressEventId(),
				event.topicId(),
				event.milestoneId(),
				event.progressLevel(),
				event.userSignal());
	}

	private static RecognizedTopicSummary toRecognizedTopicSummary(RecognizedTopic topic) {
		return new RecognizedTopicSummary(
				topic.topicId(),
				topic.milestoneVersion(),
				topic.recognizedAt());
	}
}
