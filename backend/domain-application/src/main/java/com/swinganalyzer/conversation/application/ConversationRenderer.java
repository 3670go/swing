package com.swinganalyzer.conversation.application;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Component;

import com.swinganalyzer.analysis.application.model.AiProcessingContract.CoachContent;

@Component
public class ConversationRenderer {

	public RenderedConversation render(CoachContent content) {
		List<String> messageParts = new ArrayList<>();
		messageParts.add(content.directAnswer().strip());
		if (!content.causalChain().isEmpty()) {
			messageParts.add(String.join(" → ", content.causalChain()));
		}
		if (content.singleChange() != null) {
			messageParts.add(content.singleChange().strip());
		}
		if (content.verification() != null) {
			messageParts.add(content.verification().strip());
		}

		String positiveFeedback = trimToNull(content.preserveCandidate());
		String positiveTopic = positiveFeedback == null ? null : trimToNull(content.preserveTopic());
		String followUp = followUpQuestion(content.followUpInformationNeeded());
		String questionTopic = followUp == null ? null : "follow_up_information_needed";
		String inviteMode = followUp == null ? "none" : "follow_up_experiment";

		Map<String, Object> interactionMeta = new LinkedHashMap<>();
		interactionMeta.put("response_mode", responseMode(messageParts));
		interactionMeta.put("positive_topic", positiveTopic);
		interactionMeta.put("question_topic", questionTopic);
		interactionMeta.put("invite_mode", inviteMode);

		return new RenderedConversation(
				String.join("\n\n", messageParts),
				positiveFeedback,
				positiveTopic,
				followUp,
				questionTopic,
				inviteMode,
				interactionMeta);
	}

	private static String responseMode(List<String> messageParts) {
		return messageParts.size() <= 2 ? "short" : "standard";
	}

	private static String followUpQuestion(String informationNeeded) {
		String value = trimToNull(informationNeeded);
		if (value == null) {
			return null;
		}
		String withoutPeriod = value.endsWith(".") ? value.substring(0, value.length() - 1) : value;
		return withoutPeriod + "도 알려줄래요?";
	}

	private static String trimToNull(String value) {
		if (value == null || value.isBlank()) {
			return null;
		}
		return value.strip();
	}

	public record RenderedConversation(
			String message,
			String positiveFeedback,
			String positiveTopic,
			String followUpQuestion,
			String questionTopic,
			String inviteMode,
			Map<String, Object> interactionMeta) {

		public String chatText() {
			return String.join("\n\n", visibleParts());
		}

		private List<String> visibleParts() {
			List<String> parts = new ArrayList<>();
			parts.add(message);
			if (positiveFeedback != null) {
				parts.add(positiveFeedback);
			}
			if (followUpQuestion != null) {
				parts.add(followUpQuestion);
			}
			return parts;
		}
	}
}
