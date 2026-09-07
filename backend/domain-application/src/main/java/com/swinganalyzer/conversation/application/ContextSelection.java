package com.swinganalyzer.conversation.application;

import java.util.List;

import com.swinganalyzer.analysis.application.model.AiProcessingContract.HistoryMessage;
import com.swinganalyzer.conversation.domain.RetrievedCoachingContext;

/**
 * The context selected for one AI request: the DB-backed coaching state plus the
 * recent dialogue window and the message sequence range it was taken from.
 * Produced by {@link ContextRetrievalService} and consumed by both
 * {@link ContextPacketAssembler} (to build the transport packet) and the snapshot
 * store (to record what was used).
 */
public record ContextSelection(
		RetrievedCoachingContext coachingContext,
		List<HistoryMessage> recentDialogue,
		Long messageSequenceStart,
		Long messageSequenceEnd) {

	public ContextSelection {
		coachingContext = coachingContext == null ? RetrievedCoachingContext.empty() : coachingContext;
		recentDialogue = recentDialogue == null ? List.of() : List.copyOf(recentDialogue);
	}

	public static ContextSelection empty() {
		return new ContextSelection(RetrievedCoachingContext.empty(), List.of(), null, null);
	}
}
