from typing import cast

from app.graphs.runtime import build_analysis_graph
from app.llm import ModelAdapter
from app.ports.swing_analyzer import (
    SwingAnalysisInput,
    SwingAnalysisResult,
)


class LangGraphSwingAnalyzer:
    """Execute the existing LangGraph pipeline behind the AI analysis port."""

    def __init__(self, model: ModelAdapter) -> None:
        self._model = model
        self._graph = build_analysis_graph(model)

    @property
    def is_configured(self) -> bool:
        return self._model.is_configured

    async def analyze(self, analysis_input: SwingAnalysisInput) -> SwingAnalysisResult:
        result = await self._graph.ainvoke(
            {
                "frame_paths": analysis_input.frame_paths,
                "media_kind": analysis_input.media_kind,
                "context": analysis_input.context,
                "question": analysis_input.question,
                "history": analysis_input.history,
            }
        )
        return SwingAnalysisResult(
            status=cast("str", result["status"]),
            observation=result["observation"],
            reply=result.get("reply"),
            interaction_meta=result.get("interaction_meta"),
        )
