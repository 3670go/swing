package com.swinganalyzer.conversation.application;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.swinganalyzer.analysis.application.model.AiProcessingContract.HistoryMessage;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.InteractionMeta;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.ShotContext;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.ActiveTopic;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.CoachingScope;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.Fact;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.Milestone;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.OpenLoop;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.ProgressEvent;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.Recognition;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.RecognizedTopic;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext.Roadmap;
import com.swinganalyzer.conversation.infrastructure.persistence.ChatMessageEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.ChatMessageJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.CoachingTopicEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.CoachingTopicJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.OpenLoopEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.OpenLoopJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.ProgressEventEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.ProgressEventJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.RecognitionEventEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.RecognitionEventJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.RoadmapEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.RoadmapJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.RoadmapMilestoneEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.RoadmapMilestoneJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.UserContextFactEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.UserContextFactJpaRepository;

/**
 * Selects the limited coaching state a single request may carry into an AI call.
 *
 * <p>Selection rules (Context Packet limits, 2026-08-26 MVP):
 * <ul>
 *   <li>Active topic: the owner's one {@code ACTIVE} topic, but only when its
 *       scope matches the current request scope; otherwise no topic-derived state
 *       (roadmap, pending open loop, unrecognized progress) is carried.</li>
 *   <li>Recent dialogue: last 12 messages, current user message removed.</li>
 *   <li>Completed milestones: 10. User context facts: 12 (scope filtered).</li>
 *   <li>Pending open loop: the topic's single latest {@code PENDING} loop.</li>
 *   <li>Unrecognized progress events: 10 for the in-scope active topic.</li>
 * </ul>
 * Analysis episodes have no V5 table and are left empty in Session 2. Applying
 * Coaching Turn Plan candidates is Session 3.
 */
@Service
public class ContextRetrievalService {

	static final int MAX_RECENT_DIALOGUE = 12;
	static final int MAX_COMPLETED_MILESTONES = 10;
	static final int MAX_USER_CONTEXT_FACTS = 12;
	static final int MAX_UNRECOGNIZED_PROGRESS_EVENTS = 10;
	static final int MAX_RECENTLY_RECOGNIZED_TOPICS = 10;
	private static final int DIALOGUE_FETCH = MAX_RECENT_DIALOGUE + 1;

	private final ChatMessageJpaRepository messages;
	private final CoachingTopicJpaRepository topics;
	private final RoadmapJpaRepository roadmaps;
	private final RoadmapMilestoneJpaRepository milestones;
	private final UserContextFactJpaRepository facts;
	private final ProgressEventJpaRepository progressEvents;
	private final RecognitionEventJpaRepository recognitionEvents;
	private final OpenLoopJpaRepository openLoops;

	public ContextRetrievalService(
			ChatMessageJpaRepository messages,
			CoachingTopicJpaRepository topics,
			RoadmapJpaRepository roadmaps,
			RoadmapMilestoneJpaRepository milestones,
			UserContextFactJpaRepository facts,
			ProgressEventJpaRepository progressEvents,
			RecognitionEventJpaRepository recognitionEvents,
			OpenLoopJpaRepository openLoops) {
		this.messages = messages;
		this.topics = topics;
		this.roadmaps = roadmaps;
		this.milestones = milestones;
		this.facts = facts;
		this.progressEvents = progressEvents;
		this.recognitionEvents = recognitionEvents;
		this.openLoops = openLoops;
	}

	@Transactional(readOnly = true)
	public ContextSelection retrieve(
			UUID ownerContextId,
			UUID conversationId,
			ShotContext shotContext,
			String currentUserMessage) {
		CoachingScope requestScope = new CoachingScope(
				shotContext.shotProfile(), shotContext.club(), null, shotContext.shortGameType());

		DialogueWindow dialogue = selectRecentDialogue(conversationId, currentUserMessage);

		ActiveTopic activeTopic = null;
		Roadmap roadmap = null;
		OpenLoop pendingOpenLoop = null;
		List<ProgressEvent> unrecognized = List.of();

		CoachingTopicEntity topic = topics
				.findFirstByOwnerContextIdAndStatus(ownerContextId, "ACTIVE")
				.orElse(null);
		if (topic != null && scopeOf(topic).matches(requestScope)) {
			activeTopic = toActiveTopic(topic);
			roadmap = loadRoadmap(topic.id());
			pendingOpenLoop = openLoops
					.findFirstByTopicIdAndStateOrderByCreatedAtDesc(topic.id(), "PENDING")
					.map(ContextRetrievalService::toOpenLoop)
					.orElse(null);
			unrecognized = progressEvents
					.findByOwnerContextIdAndTopicIdAndRecognizedFalseOrderByCreatedAtAsc(
							ownerContextId, topic.id(),
							PageRequest.of(0, MAX_UNRECOGNIZED_PROGRESS_EVENTS))
					.stream()
					.map(ContextRetrievalService::toProgressEvent)
					.toList();
		}

		List<Fact> selectedFacts = facts
				.findByOwnerContextIdAndSupersededAtIsNullOrderByValidFromDesc(ownerContextId)
				.stream()
				.filter(fact -> scopeOf(fact).matches(requestScope))
				.limit(MAX_USER_CONTEXT_FACTS)
				.map(ContextRetrievalService::toFact)
				.toList();

		Recognition recognition = new Recognition(
				unrecognized,
				recognitionEvents
						.findByOwnerContextIdOrderByExposedAtDesc(
								ownerContextId, PageRequest.of(0, MAX_RECENTLY_RECOGNIZED_TOPICS))
						.stream()
						.map(ContextRetrievalService::toRecognizedTopic)
						.toList(),
				recognitionEvents
						.findFirstByOwnerContextIdAndRoadmapIdIsNotNullOrderByExposedAtDesc(ownerContextId)
						.map(event -> event.exposedAt().toString())
						.orElse(null));

		RetrievedCoachingContext coachingContext = new RetrievedCoachingContext(
				activeTopic, roadmap, selectedFacts, pendingOpenLoop, recognition);
		return new ContextSelection(
				coachingContext, dialogue.messages(), dialogue.sequenceStart(), dialogue.sequenceEnd());
	}

	private Roadmap loadRoadmap(UUID topicId) {
		RoadmapEntity roadmap = roadmaps.findFirstByTopicIdAndActiveTrue(topicId).orElse(null);
		if (roadmap == null) {
			return null;
		}
		Milestone current = roadmap.currentMilestoneId() == null
				? null
				: milestones.findById(roadmap.currentMilestoneId())
						.map(ContextRetrievalService::toMilestone)
						.orElse(null);
		List<Milestone> completed = milestones
				.findByRoadmapIdAndEvidenceLevelOrderBySortOrderAsc(
						roadmap.id(), "MILESTONE_COMPLETED",
						PageRequest.of(0, MAX_COMPLETED_MILESTONES))
				.stream()
				.map(ContextRetrievalService::toMilestone)
				.toList();
		return new Roadmap(
				roadmap.id(),
				roadmap.version(),
				roadmap.targetSwing(),
				current,
				completed,
				roadmap.nextCompletionCondition());
	}

	private DialogueWindow selectRecentDialogue(UUID conversationId, String currentUserMessage) {
		List<ChatMessageEntity> newestFirst = messages.findByConversationIdOrderBySequenceNumberDesc(
				conversationId, PageRequest.of(0, DIALOGUE_FETCH));
		List<ChatMessageEntity> oldestFirst = new ArrayList<>(newestFirst);
		java.util.Collections.reverse(oldestFirst);

		if (!oldestFirst.isEmpty()) {
			ChatMessageEntity last = oldestFirst.get(oldestFirst.size() - 1);
			if ("user".equals(last.role())
					&& currentUserMessage != null
					&& currentUserMessage.equals(last.content())) {
				oldestFirst.remove(oldestFirst.size() - 1);
			}
		}
		if (oldestFirst.size() > MAX_RECENT_DIALOGUE) {
			oldestFirst = new ArrayList<>(
					oldestFirst.subList(oldestFirst.size() - MAX_RECENT_DIALOGUE, oldestFirst.size()));
		}

		List<HistoryMessage> history = new ArrayList<>();
		Long start = null;
		Long end = null;
		for (ChatMessageEntity message : oldestFirst) {
			history.add(toHistory(message));
			Long sequence = message.sequenceNumber();
			if (sequence != null) {
				start = start == null ? sequence : Math.min(start, sequence);
				end = end == null ? sequence : Math.max(end, sequence);
			}
		}
		return new DialogueWindow(history, start, end);
	}

	private static CoachingScope scopeOf(CoachingTopicEntity topic) {
		return new CoachingScope(
				topic.shotProfile(), topic.club(), topic.clubGroup(), topic.shortGameType());
	}

	private static CoachingScope scopeOf(UserContextFactEntity fact) {
		return new CoachingScope(
				fact.shotProfile(), fact.club(), fact.clubGroup(), fact.shortGameType());
	}

	private static ActiveTopic toActiveTopic(CoachingTopicEntity topic) {
		return new ActiveTopic(
				topic.id(),
				topic.version(),
				topic.userProblem(),
				topic.rootProblem(),
				scopeOf(topic),
				topic.activeHypothesis(),
				topic.currentExperiment(),
				topic.carryForwardFeel());
	}

	private static Milestone toMilestone(RoadmapMilestoneEntity milestone) {
		return new Milestone(
				milestone.id(),
				milestone.version(),
				milestone.title(),
				milestone.evidenceLevel(),
				milestone.completionCondition());
	}

	private static Fact toFact(UserContextFactEntity fact) {
		List<UUID> episodeIds = new ArrayList<>();
		for (String raw : fact.sourceEpisodeIds()) {
			try {
				episodeIds.add(UUID.fromString(raw));
			} catch (IllegalArgumentException ignored) {
				// Skip malformed ids; the source is a jsonb array under Java's control.
			}
		}
		return new Fact(
				fact.id(),
				fact.version(),
				fact.statement(),
				fact.evidenceLevel(),
				scopeOf(fact),
				episodeIds);
	}

	private static OpenLoop toOpenLoop(OpenLoopEntity openLoop) {
		return new OpenLoop(
				openLoop.id(),
				openLoop.version(),
				openLoop.carryForwardFeel(),
				openLoop.nextSingleChange(),
				openLoop.nextVerification(),
				openLoop.predictedResult());
	}

	private static ProgressEvent toProgressEvent(ProgressEventEntity event) {
		return new ProgressEvent(
				event.id(),
				event.topicId(),
				event.milestoneId(),
				event.progressLevel(),
				event.userSignal());
	}

	private static RecognizedTopic toRecognizedTopic(RecognitionEventEntity event) {
		return new RecognizedTopic(
				event.topicId(),
				event.milestoneVersion(),
				event.exposedAt() == null ? null : event.exposedAt().toString());
	}

	private static HistoryMessage toHistory(ChatMessageEntity message) {
		Map<String, Object> meta = message.interactionMeta();
		InteractionMeta interactionMeta = meta == null ? null : new InteractionMeta(
				(String) meta.get("response_mode"),
				(String) meta.get("positive_topic"),
				(String) meta.get("question_topic"),
				(String) meta.get("invite_mode"));
		return new HistoryMessage(message.role(), message.content(), interactionMeta);
	}

	private record DialogueWindow(List<HistoryMessage> messages, Long sequenceStart, Long sequenceEnd) {
	}
}
