from dataclasses import dataclass
from typing import Literal

AnalysisRunStatus = Literal[
    "running",
    "succeeded",
    "limited",
    "rejected",
    "failed",
    "deleted",
]
AnalysisCompletionStatus = Literal["succeeded", "limited", "rejected"]

ACTIVE_STATUS: AnalysisRunStatus = "running"
FAILED_STATUS: AnalysisRunStatus = "failed"
DELETED_STATUS: AnalysisRunStatus = "deleted"
REPLY_AVAILABLE_STATUSES: tuple[AnalysisRunStatus, ...] = ("succeeded", "limited")
VISIBLE_STATUSES: tuple[AnalysisRunStatus, ...] = (
    "running",
    "succeeded",
    "limited",
    "rejected",
    "failed",
)


@dataclass(frozen=True)
class AnalysisStatusTransition:
    allowed_from: tuple[AnalysisRunStatus, ...]
    target: AnalysisRunStatus


class AnalysisStatusPolicy:
    """Define legal lifecycle transitions for one analysis run."""

    @staticmethod
    def start() -> AnalysisRunStatus:
        return ACTIVE_STATUS

    @staticmethod
    def complete(status: AnalysisCompletionStatus) -> AnalysisStatusTransition:
        if status not in {"succeeded", "limited", "rejected"}:
            raise ValueError(f"Invalid analysis completion status: {status}")
        return AnalysisStatusTransition((ACTIVE_STATUS,), status)

    @staticmethod
    def fail() -> AnalysisStatusTransition:
        return AnalysisStatusTransition((ACTIVE_STATUS,), FAILED_STATUS)

    @staticmethod
    def delete() -> AnalysisStatusTransition:
        return AnalysisStatusTransition(VISIBLE_STATUSES, DELETED_STATUS)
