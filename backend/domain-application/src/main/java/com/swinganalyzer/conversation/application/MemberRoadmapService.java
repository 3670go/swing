package com.swinganalyzer.conversation.application;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.swinganalyzer.analysis.infrastructure.persistence.AnalysisRunEntity;
import com.swinganalyzer.analysis.infrastructure.persistence.AnalysisRunJpaRepository;
import com.swinganalyzer.conversation.application.MemberRoadmapService.MilestoneView;
import com.swinganalyzer.conversation.application.MemberRoadmapService.RoadmapView;
import com.swinganalyzer.conversation.infrastructure.persistence.CoachingTopicEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.CoachingTopicJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.RoadmapEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.RoadmapJpaRepository;
import com.swinganalyzer.conversation.infrastructure.persistence.RoadmapMilestoneEntity;
import com.swinganalyzer.conversation.infrastructure.persistence.RoadmapMilestoneJpaRepository;
import com.swinganalyzer.shared.error.PublicApiException;

@Service
public class MemberRoadmapService {

	private static final List<String> ROADMAP_SOURCE_STATUSES = List.of("succeeded", "limited");

	private final AnalysisRunJpaRepository analysisRuns;
	private final CoachingTopicJpaRepository topics;
	private final RoadmapJpaRepository roadmaps;
	private final RoadmapMilestoneJpaRepository milestones;

	public MemberRoadmapService(
			AnalysisRunJpaRepository analysisRuns,
			CoachingTopicJpaRepository topics,
			RoadmapJpaRepository roadmaps,
			RoadmapMilestoneJpaRepository milestones) {
		this.analysisRuns = analysisRuns;
		this.topics = topics;
		this.roadmaps = roadmaps;
		this.milestones = milestones;
	}

	@Transactional
	public RoadmapView create(UUID ownerContextId, UUID analysisRunId, String targetSwing) {
		String normalizedTargetSwing = targetSwing.strip();
		AnalysisRunEntity source = analysisRuns.findOwnedRun(analysisRunId, ownerContextId)
				.orElseThrow(() -> notFound("ANALYSIS_NOT_FOUND"));
		if (!ROADMAP_SOURCE_STATUSES.contains(source.status())) {
			throw invalidSource();
		}

		CoachingTopicEntity topic = topics.findFirstByOwnerContextIdAndStatus(ownerContextId, "ACTIVE")
				.orElseThrow(MemberRoadmapService::invalidSource);
		if (!source.conversationId().equals(topic.conversationId())) {
			throw invalidSource();
		}

		RoadmapEntity existingForTopic = roadmaps.findFirstByTopicIdAndActiveTrue(topic.id()).orElse(null);
		if (existingForTopic != null && normalizedTargetSwing.equals(existingForTopic.targetSwing())) {
			return view(existingForTopic);
		}

		RoadmapSource details = extractSource(source.reply());
		if (existingForTopic != null) {
			existingForTopic.archive();
			roadmaps.saveAndFlush(existingForTopic);
		} else {
			roadmaps.findFirstByOwnerContextIdAndActiveTrue(ownerContextId).ifPresent(previous -> {
				previous.archive();
				roadmaps.saveAndFlush(previous);
			});
		}

		RoadmapEntity roadmap = new RoadmapEntity(
				ownerContextId,
				topic.id(),
				normalizedTargetSwing,
				topic.rootProblem() == null ? topic.userProblem() : topic.rootProblem(),
				details.verification());
		roadmaps.saveAndFlush(roadmap);

		RoadmapMilestoneEntity milestone = new RoadmapMilestoneEntity(
				roadmap.id(),
				topic.id(),
				limitTitle(details.singleChange()),
				topic.rootProblem(),
				"로드맵 생성 기준 분석 완료",
				details.verification());
		milestones.saveAndFlush(milestone);
		roadmap.selectCurrentMilestone(milestone.id());
		roadmaps.save(roadmap);
		return toView(roadmap, List.of(milestone));
	}

	@Transactional(readOnly = true)
	public RoadmapView active(UUID ownerContextId) {
		return roadmaps.findFirstByOwnerContextIdAndActiveTrue(ownerContextId)
				.map(this::view)
				.orElse(null);
	}

	private RoadmapView view(RoadmapEntity roadmap) {
		return toView(roadmap, milestones.findByRoadmapIdOrderBySortOrderAsc(roadmap.id()));
	}

	private static RoadmapView toView(
			RoadmapEntity roadmap,
			List<RoadmapMilestoneEntity> roadmapMilestones) {
		List<MilestoneView> views = roadmapMilestones.stream()
				.map(milestone -> new MilestoneView(
						milestone.id(),
						milestone.version(),
						milestone.sortOrder(),
						milestone.title(),
						milestone.evidenceLevel(),
						milestone.completionCondition()))
				.toList();
		MilestoneView current = views.stream()
				.filter(milestone -> milestone.milestoneId().equals(roadmap.currentMilestoneId()))
				.findFirst()
				.orElse(null);
		return new RoadmapView(
				roadmap.id(),
				roadmap.version(),
				roadmap.targetSwing(),
				roadmap.startingState(),
				roadmap.nextCompletionCondition(),
				current,
				views);
	}

	private static RoadmapSource extractSource(Map<String, Object> reply) {
		if (reply == null || !(reply.get("content") instanceof Map<?, ?> content)) {
			throw invalidSource();
		}
		String singleChange = text(content.get("single_change"));
		if (singleChange == null) {
			singleChange = text(content.get("singleChange"));
		}
		String verification = text(content.get("verification"));
		if (singleChange == null || verification == null) {
			throw invalidSource();
		}
		return new RoadmapSource(singleChange, verification);
	}

	private static String text(Object value) {
		if (!(value instanceof String text) || text.isBlank()) {
			return null;
		}
		return text.strip();
	}

	private static String limitTitle(String title) {
		return title.length() <= 200 ? title : title.substring(0, 200);
	}

	private static PublicApiException invalidSource() {
		return new PublicApiException(HttpStatus.UNPROCESSABLE_CONTENT, "ROADMAP_SOURCE_INCOMPLETE");
	}

	private static PublicApiException notFound(String detail) {
		return new PublicApiException(HttpStatus.NOT_FOUND, detail);
	}

	private record RoadmapSource(String singleChange, String verification) {
	}

	public record MilestoneView(
			UUID milestoneId,
			int version,
			int sortOrder,
			String title,
			String evidenceLevel,
			String completionCondition) {
	}

	public record RoadmapView(
			UUID roadmapId,
			int version,
			String targetSwing,
			String startingState,
			String nextCompletionCondition,
			MilestoneView currentMilestone,
			List<MilestoneView> milestones) {
	}
}
