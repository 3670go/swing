"""CLI: fixture JSON 을 읽어 ConversationState JSON 을 출력한다.

python main.py --fixture fixtures/01_acknowledgement_without_baseline.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from schemas import ConversationInput, InputIntegrityError, TrackerError
from state_tracker import track

EXIT_OK = 0
EXIT_TRACKER_ERROR = 1
EXIT_INVALID_INPUT = 2

FIXED_NOW = datetime.fromisoformat("2026-08-28T12:00:00+09:00")
"""CLI 출력을 재현 가능하게 만들기 위한 고정 시각."""


def load_input(path: Path) -> ConversationInput:
    return ConversationInput.model_validate_json(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Conversation state tracker POC")
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--full", action="store_true", help="전체 상태를 출력한다")
    args = parser.parse_args(argv)

    try:
        payload = load_input(args.fixture)
    except (ValidationError, ValueError) as error:
        print(f"invalid fixture: {error}", file=sys.stderr)
        return EXIT_INVALID_INPUT

    try:
        state = track(payload, now=FIXED_NOW)
    except InputIntegrityError as error:
        print(f"invalid fixture: {type(error).__name__}: {error}", file=sys.stderr)
        return EXIT_INVALID_INPUT
    except TrackerError as error:
        print(f"tracker failed: {type(error).__name__}: {error}", file=sys.stderr)
        return EXIT_TRACKER_ERROR

    dumped = state.model_dump(mode="json")
    if not args.full:
        dumped = {
            "explicit_intent": dumped["explicit_intent"],
            "engagement_state": {
                "level": dumped["engagement_state"]["level"],
                "trend": dumped["engagement_state"]["trend"],
                "confidence": dumped["engagement_state"]["confidence"],
            },
            "inferred_needs": [
                {"need_type": need["need_type"], "confidence": need["confidence"]}
                for need in dumped["inferred_needs"]
            ],
            "progress": {
                "level": dumped["progress"]["level"],
                "confidence": dumped["progress"]["confidence"],
                "swing_improvement_confirmed": dumped["progress"]["swing_improvement_confirmed"],
                "recognition_intensity_cap": dumped["progress"]["recognition_intensity_cap"],
            },
            "next_response_strategy": dumped["next_response_strategy"],
            "secondary_strategy": dumped["secondary_strategy"],
            "selected_context_message_ids": dumped["selected_context_message_ids"],
            "unresolved_open_loops": [
                {"open_loop_id": loop["open_loop_id"], "topic_id": loop["topic_id"]}
                for loop in dumped["unresolved_open_loops"]
            ],
        }
    print(json.dumps(dumped, ensure_ascii=False, indent=2))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
