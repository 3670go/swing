package com.swinganalyzer.analysis.application;

import com.swinganalyzer.analysis.application.model.AiProcessingContract.AnalysisRequest;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.AnalysisResponse;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.HealthResponse;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.TextCoachingRequest;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.TextCoachingResponse;

public interface AiProcessingClient {

	HealthResponse health();

	AnalysisResponse analyze(AnalysisRequest request);

	TextCoachingResponse coachText(TextCoachingRequest request);
}
