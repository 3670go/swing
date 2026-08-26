package com.swinganalyzer.shared.api;

import com.swinganalyzer.analysis.application.model.AiProcessingContract.ShotContext;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record ShotContextRequest(
		@NotNull @Pattern(regexp = "full_swing|short_game") String shotProfile,
		@NotBlank @Size(max = 64) String club,
		@NotNull @Pattern(regexp = "face_on|down_the_line") String cameraView,
		@NotNull @Pattern(regexp = "right|left") String handedness,
		@NotNull @Pattern(regexp = "posture_correction|shot_result|comparison") String analysisGoal,
		@Size(max = 64) String shortGameType,
		@Size(max = 64) String videoType,
		@Size(max = 128) String shotResult) {

	public ShotContext toInternal() {
		return new ShotContext(
				shotProfile,
				club,
				cameraView,
				handedness,
				analysisGoal,
				shortGameType,
				videoType,
				shotResult);
	}
}
