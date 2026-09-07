package com.swinganalyzer.conversation.application;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.swinganalyzer.analysis.application.model.AiProcessingContract.CoachingTopicCandidate;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.CoachingTurnPlan;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.EvidenceReference;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.OpenLoopCandidate;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.ProblemReframeCandidate;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.ProgressCandidate;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.RecognitionCandidate;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.RoadmapUpdateCandidate;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.Milestone;
import com.swinganalyzer.conversation.infrastructure.persistence.CoachingRequestApplicationEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.CoachingRequestApplicationJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.CoachingTopicEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.CoachingTopicJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.OpenLoopEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.OpenLoopJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.ProgressEventEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.ProgressEventJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.RecognitionEventEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.RecognitionEventJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.RoadmapMilestoneEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.RoadmapMilestoneJpaRepository;

/**
 * Applies validated Coaching Turn Plan candidates to Java-owned product state.
 *
 * <p>Java owns product state and does not trust the plan verbatim. All candidates
 * pass one common boundary before any write:
 * <ol>
 *   <li>Idempotency: a {@code request_id} already recorded in
 *       {@code coaching_request_applications} is never applied twice.</li>
 *   <li>Version guard: a candidate whose expected version disagrees with the
 *       ContextSnapshot version blocks the whole request ({@code VERSION_MISMATCH}).</li>
 *   <li>Evidence guard: a candidate is skipped unless every one of its evidence
 *       references points to a source present in the ContextPacket / this turn's
 *       observations.</li>
 *   <li>Evidence-level guard: a video-level progress/milestone transition is
 *       skipped without observation evidence, and recognition intensity is clamped
 *       when the turn has no video evidence.</li>
 * </ol>
 *
 * <p>Session 3 minimal scope: problem reframe, milestone evidence promotion,
 * progress event, recognition, and open loop. Deferred to a later session:
 * topic {@code CREATE_NEW}/{@code ACTIVATE_EXISTING}/{@code RESOLVE_CURRENT}
 * transitions, roadmap/milestone {@code CREATE}/{@code UPDATE}, and final response
 * roadmap-card assembly. The public response shape is unchanged.
 */
@Service
public class CoachingPlanApplicationService {

	private static final Map<String, Integer> EVIDENCE_RANK = Map.of(
			"NOT_STARTED", 0,
			"USER_REPORTED_PROGRESS", 1,
			"RESULT_REPEATED", 2,
			"VIDEO_VERIFIED_PROGRESS", 3,
			"MILESTONE_COMPLETED", 4);
	private static final Map<String, Integer> INTENSITY_RANK = Map.of(
			"ACKNOWLEDGEMENT", 0,
			"SPECIFIC_RECOGNITION", 1,
			"PROGRESS_DECLARATION", 2,
			"IDENTITY_CONNECTION", 3);
	private static final int MAX_INTENSITY_WITHOUT_VIDEO = 1; // SPECIFIC_RECOGNITION

	private final CoachingRequestApplicationJpaRepository applications;
	private final CoachingTopicJpaRepository topics;
	private final RoadmapMilestoneJpaRepository milestones;
	private final ProgressEventJpaRepository progressEvents;
	private final RecognitionEventJpaRepository recognitionEvents;
	private final OpenLoopJpaRepository openLoops;

	public CoachingPlanApplicationService(
			CoachingRequestApplicationJpaRepository applications,
			CoachingTopicJpaRepository topics,
			RoadmapMilestoneJpaRepository milestones,
			ProgressEventJpaRepository progressEvents,
			RecognitionEventJpaRepository recognitionEvents,
			OpenLoopJpaRepository openLoops) {
		this.applications = applications;
		this.topics = topics;
		this.milestones = milestones;
		this.progressEvents = progressEvents;
		this.recognitionEvents = recognitionEvents;
		this.openLoops = openLoops;
	}

	@Transactional
	public ApplicationOutcome apply(ApplicationCommand command) {
		CoachingTurnPlan plan = command.plan();
		if (plan == null) {
			return ApplicationOutcome.skipped();
		}
		if (applications.existsById(command.requestId())) {
			return ApplicationOutcome.duplicate();
		}

		Versions versions = Versions.from(command.selection());
		if (versionMismatch(plan, versions)) {
			applications.save(blocked(command, CoachingRequestApplicationEntity.VERSION_MISMATCH));
			return ApplicationOutcome.blocked(CoachingRequestApplicationEntity.VERSION_MISMATCH);
		}

		EvidenceSet evidence = EvidenceSet.from(command.selection(), command.observationCount());
		RetrievedCoachingContext coaching = command.selection().coachingContext();
		UUID topicId = coaching.activeTopic() == null ? null : coaching.activeTopic().topicId();
		UUID roadmapId = coaching.roadmap() == null ? null : coaching.roadmap().roadmapId();

		ApplicationOutcome.Builder outcome = ApplicationOutcome.builder();

		applyReframe(plan, evidence, command.ownerId(), outcome);
		applyMilestone(plan, evidence, outcome);
		ProgressEventEntity progress = applyProgress(
				plan, evidence, command.ownerId(), topicId, outcome);
		applyRecognition(plan, evidence, command.ownerId(), topicId, roadmapId, progress, versions, outcome);
		applyOpenLoop(plan, command.ownerId(), topicId, outcome);

		applications.save(applied(command));
		return outcome.build();
	}

	// --- reframe --------------------------------------------------------------

	private void applyReframe(
			CoachingTurnPlan plan, EvidenceSet evidence, UUID ownerId, ApplicationOutcome.Builder outcome) {
		CoachingTopicCandidate topicCandidate = plan.coachingTopicCandidate();
		ProblemReframeCandidate reframe = plan.problemReframeCandidate();
		if (topicCandidate == null || !"REFRAME_CURRENT".equals(topicCandidate.action()) || reframe == null) {
			return;
		}
		if (!evidence.allValid(reframe.evidenceReferences())) {
			return;
		}
		// The plan never carries the owner; resolve the owner's ACTIVE topic. The
		// version was already verified against the snapshot for this owner.
		CoachingTopicEntity topic = topics
				.findFirstByOwnerContextIdAndStatus(ownerId, "ACTIVE")
				.orElse(null);
		if (topic == null) {
			return;
		}
		topic.reframe(reframe.proposedRootProblem());
		topics.save(topic);
		outcome.reframeApplied();
	}

	// --- milestone evidence promotion ----------------------------------------

	private void applyMilestone(CoachingTurnPlan plan, EvidenceSet evidence, ApplicationOutcome.Builder outcome) {
		for (RoadmapUpdateCandidate candidate : plan.roadmapUpdateCandidates()) {
			if (!"MILESTONE".equals(candidate.targetType()) || candidate.targetId() == null) {
				continue;
			}
			String targetLevel = milestoneLevelFor(candidate.proposedTransition());
			if (targetLevel == null || !evidence.allValid(candidate.evidenceReferences())) {
				continue;
			}
			if (requiresVideo(targetLevel) && !evidence.hasObservationEvidence(candidate.evidenceReferences())) {
				continue;
			}
			RoadmapMilestoneEntity milestone = milestones.findById(candidate.targetId()).orElse(null);
			if (milestone == null || !isPromotion(milestone.evidenceLevel(), targetLevel)) {
				continue;
			}
			milestone.promoteEvidence(targetLevel);
			milestones.save(milestone);
			outcome.milestoneApplied();
		}
	}

	private static String milestoneLevelFor(String transition) {
		return switch (transition) {
			case "MARK_USER_REPORTED_PROGRESS" -> "USER_REPORTED_PROGRESS";
			case "MARK_RESULT_REPEATED" -> "RESULT_REPEATED";
			case "MARK_VIDEO_VERIFIED_PROGRESS" -> "VIDEO_VERIFIED_PROGRESS";
			case "COMPLETE" -> "MILESTONE_COMPLETED";
			default -> null; // CREATE / UPDATE deferred
		};
	}

	// --- progress -------------------------------------------------------------

	private ProgressEventEntity applyProgress(
			CoachingTurnPlan plan,
			EvidenceSet evidence,
			UUID ownerId,
			UUID topicId,
			ApplicationOutcome.Builder outcome) {
		ProgressCandidate candidate = plan.progressCandidate();
		if (candidate == null || topicId == null) {
			return null;
		}
		if (!evidence.allValid(candidate.evidenceReferences())) {
			return null;
		}
		if (requiresVideo(candidate.progressLevel())
				&& !evidence.hasObservationEvidence(candidate.evidenceReferences())) {
			// User-reported evidence must not be promoted to confirmed video progress.
			return null;
		}
		ProgressEventEntity progress = new ProgressEventEntity(
				ownerId, topicId, candidate.targetMilestoneId(),
				candidate.progressLevel(), candidate.userSignal());
		progressEvents.save(progress);
		outcome.progressApplied();
		return progress;
	}

	// --- recognition ----------------------------------------------------------

	private void applyRecognition(
			CoachingTurnPlan plan,
			EvidenceSet evidence,
			UUID ownerId,
			UUID topicId,
			UUID roadmapId,
			ProgressEventEntity progress,
			Versions versions,
			ApplicationOutcome.Builder outcome) {
		RecognitionCandidate candidate = plan.recognitionCandidate();
		// A recognition is tied to a progress event; without one created this turn we
		// have nothing to attach it to (progress_event_id is NOT NULL).
		if (candidate == null || progress == null) {
			return;
		}
		boolean hasVideo = plan.progressCandidate() != null
				&& evidence.hasObservationEvidence(plan.progressCandidate().evidenceReferences());
		String intensity = clampIntensity(candidate.proposedIntensity(), hasVideo);
		Integer milestoneVersion = progress.milestoneId() == null
				? null : versions.milestoneVersion(progress.milestoneId());
		recognitionEvents.save(new RecognitionEventEntity(
				ownerId, topicId, progress.id(), roadmapId, progress.milestoneId(), milestoneVersion,
				intensity, candidate.target(), candidate.recognitionContent()));
		progress.markRecognized();
		progressEvents.save(progress);
		outcome.recognitionApplied();
	}

	private static String clampIntensity(String proposed, boolean hasVideo) {
		if (hasVideo) {
			return proposed;
		}
		int rank = INTENSITY_RANK.getOrDefault(proposed, 0);
		if (rank <= MAX_INTENSITY_WITHOUT_VIDEO) {
			return proposed;
		}
		return "SPECIFIC_RECOGNITION";
	}

	// --- open loop ------------------------------------------------------------

	private void applyOpenLoop(
			CoachingTurnPlan plan, UUID ownerId, UUID topicId, ApplicationOutcome.Builder outcome) {
		OpenLoopCandidate candidate = plan.openLoopCandidate();
		if (candidate == null || topicId == null) {
			return;
		}
		openLoops.findFirstByTopicIdAndStateOrderByCreatedAtDesc(topicId, "PENDING")
				.ifPresent(existing -> {
					// Flush the REPLACED update before inserting the new PENDING loop.
					// Hibernate orders INSERTs before UPDATEs within a transaction, which
					// would otherwise leave two PENDING rows momentarily and violate
					// ux_open_loops_one_pending_per_topic on PostgreSQL.
					existing.markReplaced();
					openLoops.saveAndFlush(existing);
				});
		openLoops.save(new OpenLoopEntity(
				ownerId,
				topicId,
				candidate.carryForwardFeel(),
				candidate.nextSingleChange(),
				candidate.nextVerification(),
				candidate.completionCondition(),
				candidate.predictedResult(),
				candidate.question()));
		outcome.openLoopApplied();
	}

	// --- version guard --------------------------------------------------------

	private boolean versionMismatch(CoachingTurnPlan plan, Versions versions) {
		CoachingTopicCandidate topicCandidate = plan.coachingTopicCandidate();
		if (topicCandidate != null && "REFRAME_CURRENT".equals(topicCandidate.action())) {
			if (versions.topicVersion() == null
					|| !versions.topicVersion().equals(topicCandidate.expectedVersion())) {
				return true;
			}
		}
		ProgressCandidate progress = plan.progressCandidate();
		if (progress != null) {
			Integer current = versions.milestoneVersion(progress.targetMilestoneId());
			if (current == null || current != progress.expectedVersion()) {
				return true;
			}
		}
		for (RoadmapUpdateCandidate candidate : plan.roadmapUpdateCandidates()) {
			if (!"MILESTONE".equals(candidate.targetType())
					|| milestoneLevelFor(candidate.proposedTransition()) == null) {
				continue;
			}
			Integer current = versions.milestoneVersion(candidate.targetId());
			if (current == null || !current.equals(candidate.expectedVersion())) {
				return true;
			}
		}
		return false;
	}

	private static boolean requiresVideo(String level) {
		return "VIDEO_VERIFIED_PROGRESS".equals(level) || "MILESTONE_COMPLETED".equals(level);
	}

	private static boolean isPromotion(String current, String next) {
		return EVIDENCE_RANK.getOrDefault(next, 0) > EVIDENCE_RANK.getOrDefault(current, 0);
	}

	private CoachingRequestApplicationEntity applied(ApplicationCommand command) {
		return CoachingRequestApplicationEntity.applied(
				command.requestId(), command.ownerId(), command.conversationId(),
				command.analysisRunId(), command.snapshotId());
	}

	private CoachingRequestApplicationEntity blocked(ApplicationCommand command, String reason) {
		return CoachingRequestApplicationEntity.blocked(
				command.requestId(), command.ownerId(), command.conversationId(),
				command.analysisRunId(), command.snapshotId(), reason);
	}

	// --- helper types ---------------------------------------------------------

	/** Snapshot versions the candidates are validated against. */
	private record Versions(Integer topicVersion, Map<UUID, Integer> milestoneVersions) {

		static Versions from(ContextSelection selection) {
			RetrievedCoachingContext coaching = selection.coachingContext();
			Integer topicVersion = coaching.activeTopic() == null ? null : coaching.activeTopic().version();
			Map<UUID, Integer> milestoneVersions = new HashMap<>();
			if (coaching.roadmap() != null) {
				Milestone current = coaching.roadmap().currentMilestone();
				if (current != null) {
					milestoneVersions.put(current.milestoneId(), current.version());
				}
				for (Milestone milestone : coaching.roadmap().completedMilestones()) {
					milestoneVersions.put(milestone.milestoneId(), milestone.version());
				}
			}
			return new Versions(topicVersion, milestoneVersions);
		}

		Integer milestoneVersion(UUID milestoneId) {
			return milestoneId == null ? null : milestoneVersions.get(milestoneId);
		}
	}

	/** Valid evidence source ids, derived from the ContextPacket selection. */
	private record EvidenceSet(
			Set<String> messages,
			Set<String> observations,
			Set<String> analysisEpisodes,
			Set<String> progressEvents,
			Set<String> roadmapMilestones) {

		static EvidenceSet from(ContextSelection selection, int observationCount) {
			RetrievedCoachingContext coaching = selection.coachingContext();
			Set<String> observations = new java.util.HashSet<>();
			for (int index = 0; index < observationCount; index++) {
				observations.add("observation:" + index);
			}
			Set<String> progressEvents = coaching.recognition().unrecognizedProgressEvents().stream()
					.map(event -> event.progressEventId().toString())
					.collect(Collectors.toSet());
			Set<String> milestones = new java.util.HashSet<>();
			if (coaching.roadmap() != null) {
				if (coaching.roadmap().currentMilestone() != null) {
					milestones.add(coaching.roadmap().currentMilestone().milestoneId().toString());
				}
				coaching.roadmap().completedMilestones()
						.forEach(milestone -> milestones.add(milestone.milestoneId().toString()));
			}
			Set<String> episodes = coaching.facts().stream()
					.flatMap(fact -> fact.sourceEpisodeIds().stream())
					.map(UUID::toString)
					.collect(Collectors.toSet());
			return new EvidenceSet(Set.of("current-user-message"), observations, episodes, progressEvents,
					milestones);
		}

		boolean allValid(List<EvidenceReference> references) {
			if (references == null || references.isEmpty()) {
				return false;
			}
			return references.stream().allMatch(this::isValid);
		}

		boolean hasObservationEvidence(List<EvidenceReference> references) {
			if (references == null) {
				return false;
			}
			return references.stream()
					.anyMatch(reference -> "OBSERVATION".equals(reference.sourceType()) && isValid(reference));
		}

		private boolean isValid(EvidenceReference reference) {
			return switch (reference.sourceType()) {
				case "MESSAGE" -> messages.contains(reference.sourceId());
				case "OBSERVATION" -> observations.contains(reference.sourceId());
				case "ANALYSIS_EPISODE" -> analysisEpisodes.contains(reference.sourceId());
				case "PROGRESS_EVENT" -> progressEvents.contains(reference.sourceId());
				case "ROADMAP_MILESTONE" -> roadmapMilestones.contains(reference.sourceId());
				default -> false;
			};
		}
	}

	/**
	 * Command carrying everything needed to apply a plan. The owner id is supplied
	 * by the caller (which owns product state), never taken from the plan.
	 */
	public record ApplicationCommand(
			UUID requestId,
			UUID ownerId,
			UUID conversationId,
			UUID analysisRunId,
			UUID snapshotId,
			ContextSelection selection,
			CoachingTurnPlan plan,
			int observationCount) {
	}

	/** Traceable result: which candidate kinds were applied, or why blocked. */
	public record ApplicationOutcome(
			boolean applied,
			String blockedReason,
			boolean reframeApplied,
			boolean milestoneApplied,
			boolean progressApplied,
			boolean recognitionApplied,
			boolean openLoopApplied) {

		static ApplicationOutcome duplicate() {
			return new ApplicationOutcome(false, CoachingRequestApplicationEntity.DUPLICATE_REQUEST_ID,
					false, false, false, false, false);
		}

		static ApplicationOutcome blocked(String reason) {
			return new ApplicationOutcome(false, reason, false, false, false, false, false);
		}

		static ApplicationOutcome skipped() {
			return new ApplicationOutcome(false, null, false, false, false, false, false);
		}

		static Builder builder() {
			return new Builder();
		}

		static final class Builder {
			private boolean reframe;
			private boolean milestone;
			private boolean progress;
			private boolean recognition;
			private boolean openLoop;

			void reframeApplied() {
				this.reframe = true;
			}

			void milestoneApplied() {
				this.milestone = true;
			}

			void progressApplied() {
				this.progress = true;
			}

			void recognitionApplied() {
				this.recognition = true;
			}

			void openLoopApplied() {
				this.openLoop = true;
			}

			ApplicationOutcome build() {
				return new ApplicationOutcome(
						true, null, reframe, milestone, progress, recognition, openLoop);
			}
		}
	}
}
