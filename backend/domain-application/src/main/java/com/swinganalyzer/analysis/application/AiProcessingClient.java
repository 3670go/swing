package com.swinganalyzer.analysis.application;

import com.swinganalyzer.analysis.application.model.AiProcessingContract.HealthResponse;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.InternalAnalysisRequest;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.InternalAnalysisResponse;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.InternalTextCoachingRequest;
import com.swinganalyzer.analysis.application.model.AiProcessingContract.InternalTextCoachingResponse;

public interface AiProcessingClient {

	HealthResponse health();

	InternalAnalysisResponse analyze(InternalAnalysisRequest request);

	InternalTextCoachingResponse coachText(InternalTextCoachingRequest request);
}
