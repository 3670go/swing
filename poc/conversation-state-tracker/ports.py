"""외부 의존 Port 정의.

POC 는 이 Port 의 구현체를 만들지 않고 호출하지도 않는다.
운영 Gemini 연결과 LangGraph 를 건드리지 않기 위한 경계 선언이다.
"""

from __future__ import annotations

from typing import Protocol

from schemas import ConversationInput, InferredNeed


class NeedInterpreterPort(Protocol):
    """LLM 기반 니즈 해석기의 자리.

    구현체는 이번 POC 범위 밖이다. 테스트는 결정적 규칙만 검증한다.
    구현할 때도 근거 없는 InferredNeed 를 만들면 안 된다.
    """

    def interpret(self, payload: ConversationInput) -> list[InferredNeed]: ...
