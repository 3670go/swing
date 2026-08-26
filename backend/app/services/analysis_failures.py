from typing import Literal

from app.graphs.runtime import GraphContractError
from app.llm import ModelCallError, ModelNotConfiguredError
from app.media_processing import MediaProcessingError
from app.repositories.owner_conversations import OwnerAccessError
from app.services.media_preparation import MediaPreparationError
from app.storage import StorageSigningError

AnalysisFailureKind = Literal[
    "invalid_input",
    "unsupported_media",
    "too_large",
    "not_found",
    "media_decode",
    "dependency",
    "not_configured",
]


class AnalysisUseCaseError(RuntimeError):
    """Transport-neutral failure returned by the media-analysis application boundary."""

    def __init__(self, error_code: str, kind: AnalysisFailureKind) -> None:
        super().__init__(error_code)
        self.error_code = error_code
        self.kind = kind


class AnalysisFailurePolicy:
    """Map technical failures to the stable application error contract."""

    def from_error(self, error: Exception) -> AnalysisUseCaseError:
        if isinstance(error, MediaPreparationError):
            return AnalysisUseCaseError(error.error_code, error.kind)
        if isinstance(error, OwnerAccessError):
            return AnalysisUseCaseError(str(error), "not_found")
        if isinstance(error, StorageSigningError):
            return AnalysisUseCaseError("STORAGE_UNAVAILABLE", "dependency")
        if isinstance(error, MediaProcessingError):
            return AnalysisUseCaseError("MEDIA_DECODE_FAILED", "media_decode")
        if isinstance(error, (GraphContractError, ModelCallError, ModelNotConfiguredError)):
            error_code = getattr(error, "error_code", "MODEL_UNAVAILABLE")
            return AnalysisUseCaseError(error_code, "dependency")
        raise TypeError(f"Unsupported analysis failure: {type(error).__name__}")
