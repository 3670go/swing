"""사용자 개인 표현 기준선.

표본이 부족하면 기준선을 만들지 않는다. 기준선이 없으면 스타일 기반 추정을 전부 차단한다.
"""

from __future__ import annotations

import re

from schemas import (
    BehaviorEvent,
    BehaviorEventType,
    Message,
    StyleBaseline,
)

BASELINE_MIN_HISTORICAL_MESSAGES = 6
"""기준선 계산 pool(최근 구간 제외 후)에 필요한 최소 사용자 메시지 수.

POC 가설값이다(2026-08-28). 실제 사용자 데이터로 검증되지 않았다.
계약 §9.4 의 "현재 topic 최근 메시지 최대 12개"의 절반을 임의로 취한 값이다.
"""

BASELINE_RECENT_EXCLUSION = 3
"""기준선 계산에서 제외하는 최근 사용자 메시지 수.

POC 가설값이다. 최근 반응의 변화를 탐지하려면 기준선이 그 반응에 오염되면 안 된다.
"""

BASELINE_MIN_TOTAL_USER_MESSAGES = BASELINE_MIN_HISTORICAL_MESSAGES + BASELINE_RECENT_EXCLUSION
"""기준선이 실제로 생성되기 위해 필요한 전체 사용자 메시지 수(= 9).

최근 구간을 먼저 제외한 뒤 pool 크기를 검사하므로, 전체 메시지가 이 값 미만이면
BASELINE_MIN_HISTORICAL_MESSAGES 를 넘겨도 기준선이 만들어지지 않는다.
이 상수를 두는 이유는 그 사실을 코드와 문서에서 같은 값으로 말하기 위해서다.
"""

SHORT_REPLY_RATIO = 0.4
"""기준선 평균 길이 대비 이 비율 미만이면 짧은 반응으로 본다. POC 가설값이다."""

BARE_ACKNOWLEDGEMENTS: frozenset[str] = frozenset(
    {
        "네",
        "넵",
        "넹",
        "ㅇㅋ",
        "ㅇㅇ",
        "알겠어요",
        "알겠습니다",
        "알겠어",
        "ㅋㅋ",
        "ㅋㅋㅋ",
        "아니",
        "오케이",
        "ok",
    }
)
"""단독 확인 표현.

이 집합은 하나의 부류로만 취급한다. 원소별 긍정/부정 점수를 두지 않는다.
`넵`이 `네`보다 긍정적으로 판정될 수 있는 분기를 코드에 만들지 않기 위한 장치다.
"""

PROFANITY_TOKENS: frozenset[str] = frozenset(
    {"씨발", "시발", "ㅅㅂ", "존나", "졸라", "개같", "빡치", "ㅈㄴ", "미친"}
)

POLITE_ENDINGS = ("요", "요.", "다.", "습니다", "습니다.", "니까", "세요", "세요.")

_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """비교용 정규화. 원본 메시지는 변경하지 않는다."""
    return _WHITESPACE.sub("", text.strip().rstrip("!.~").lower())


def is_bare_acknowledgement(text: str) -> bool:
    """단독 확인 표현인지. 어떤 확인 표현인지는 구분하지 않는다."""
    return normalize(text) in BARE_ACKNOWLEDGEMENTS


def contains_profanity(text: str) -> bool:
    return any(token in text for token in PROFANITY_TOKENS)


def user_messages(messages: list[Message]) -> list[Message]:
    return [message for message in messages if message.role == "user"]


def _is_question(text: str) -> bool:
    return "?" in text or text.rstrip().endswith(("나요", "까요", "가요", "어때", "야"))


def _is_elaboration(text: str) -> bool:
    """부연 설명 여부. 두 문장 이상이거나 접속 표현을 포함한다."""
    if any(token in text for token in ("그리고", "근데", "그런데", "왜냐", "그래서")):
        return True
    return len([part for part in re.split(r"[.!?\n]", text) if part.strip()]) >= 2


def _is_polite(text: str) -> bool:
    return text.rstrip().endswith(POLITE_ENDINGS)


def build_style_baseline(
    messages: list[Message],
    behavior_events: list[BehaviorEvent],
) -> StyleBaseline | None:
    """사용자 기준선을 만든다. 표본이 부족하면 None 을 돌려준다.

    최근 BASELINE_RECENT_EXCLUSION 개의 사용자 메시지는 기준선 계산에서 제외한다.
    전체 사용자 메시지가 BASELINE_MIN_TOTAL_USER_MESSAGES 개 미만이면 만들지 않는다.
    """
    everything = user_messages(messages)
    if len(everything) < BASELINE_MIN_TOTAL_USER_MESSAGES:
        return None
    pool = everything[:-BASELINE_RECENT_EXCLUSION] if BASELINE_RECENT_EXCLUSION else everything
    if len(pool) < BASELINE_MIN_HISTORICAL_MESSAGES:
        return None

    size = len(pool)
    acknowledgements = sorted(
        {normalize(message.text) for message in pool if is_bare_acknowledgement(message.text)}
    )
    return StyleBaseline(
        sample_size=size,
        average_message_length=round(sum(len(m.text) for m in pool) / size, 2),
        frequent_acknowledgements=acknowledgements,
        polite_form_ratio=round(sum(1 for m in pool if _is_polite(m.text)) / size, 3),
        question_ratio=round(sum(1 for m in pool if _is_question(m.text)) / size, 3),
        elaboration_ratio=round(sum(1 for m in pool if _is_elaboration(m.text)) / size, 3),
        video_upload_count=sum(
            1 for e in behavior_events if e.event_type is BehaviorEventType.VIDEO_UPLOADED
        ),
        practice_report_count=sum(
            1 for e in behavior_events if e.event_type is BehaviorEventType.PRACTICE_RESULT_REPORTED
        ),
        profanity_ratio=round(sum(1 for m in pool if contains_profanity(m.text)) / size, 3),
    )


def recent_short_reply_streak(messages: list[Message], baseline: StyleBaseline) -> list[Message]:
    """기준선 대비 짧은 반응이 연속으로 이어진 최근 구간을 돌려준다."""
    threshold = baseline.average_message_length * SHORT_REPLY_RATIO
    streak: list[Message] = []
    for message in reversed(user_messages(messages)):
        if len(message.text) < threshold:
            streak.append(message)
        else:
            break
    return list(reversed(streak))


def is_habitual_profanity(baseline: StyleBaseline | None) -> bool:
    """평소에도 욕설을 쓰는 사용자인지. 기준선이 없으면 판단하지 않는다."""
    return baseline is not None and baseline.profanity_ratio >= 0.3
