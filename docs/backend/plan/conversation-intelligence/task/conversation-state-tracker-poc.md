# 작업지시서 — 대화 상태 추적 및 사용자 니즈 추론 POC

> 위치: `backend` → `conversation-intelligence` → `conversation-state-tracker-poc`
>
> 상태: 계획 대기 (사용자 confirm 전 코드 작성 금지)

## 1. 작업 목표

Swing Analyzer에서 사용자의 단일 문장만 보고 감정이나 니즈를 단정하지 않고, 다음 정보를 누적해 대화 상태를 추적하는 POC를 만든다.

- 사용자가 직접 표현한 요청
- 현재 코칭 주제
- 사용자별 평소 표현 방식
- 최근 대화 참여도 변화
- 추정되는 숨은 니즈
- 추정 근거와 확신도
- 답변에 대한 사용자 피드백
- 이후 영상 업로드 및 연습 결과

이 POC의 핵심 질문은 다음과 같다.

`네`, `넵`, `ㅇㅋ` 같은 짧은 답변을 단독으로 해석하지 않고, 사용자 기준선과 앞뒤 대화 및 행동을 이용해 다음 대화 전략을 선택할 수 있는가?

## 2. 작업 위치

프로젝트:

```text
C:\Users\user\Desktop\스윙분석기
```

POC 제안 위치:

```text
C:\Users\user\Desktop\스윙분석기\poc\conversation-state-tracker
```

기존 운영 코드를 건드리지 않는 독립 POC로 만든다.

## 3. 작업 전 필수 절차

다음 파일을 먼저 확인한다.

```text
C:\Users\user\Desktop\스윙분석기\AGENTS.md
C:\Users\user\Desktop\스윙분석기\backend\contracts\context-aware-coaching-contract.md
C:\Users\user\Desktop\스윙분석기\backend\contracts\internal-api.openapi.yaml
```

확인 후 바로 구현하지 말고 먼저 다음을 출력한다.

- 생성할 파일
- 입력 및 출력 스키마
- 상태 추적 방식
- 테스트 fixture 목록
- 기존 코드와 격리되는 방법
- 실패 경로
- 검증 방법

계획을 출력한 뒤 사용자 confirm을 기다린다.

## 4. 기획 배경

### 4.1 사전 사용자 데이터

유튜브 댓글과 기존 골프 질문 데이터는 초기 질문 유형을 만드는 참고 자료로만 사용한다.
사전 데이터만으로 실제 사용자의 니즈를 확정하지 않는다. 실제 니즈는 앱 사용 중 발생하는 다음 행동으로 갱신한다.

- 추가 질문
- 반복 질문
- 영상 재업로드
- 연습 결과 보고
- 답변 평가
- 이전 교정 방법의 재사용

이번 POC에서는 외부 댓글 수집을 새로 구현하지 않는다.

### 4.2 채팅 히스토리

대화 원문과 AI가 추출한 사용자 상태를 분리한다.
원문 메시지는 수정하지 않고 유지한다. 추정된 니즈나 참여도는 별도 파생 데이터로 저장한다.

### 4.3 답변 피드백

단순 좋아요를 분석 정확성으로 취급하지 않는다.
다음과 같은 피드백을 독립 이벤트로 처리한다.

- 도움 됐어요
- 이해하기 어려워요
- 내 문제와 달라요
- 문제를 정확히 짚음
- 설명이 이해하기 쉬움
- 바로 연습할 수 있음
- 실제로 해보니 좋아짐
- 답변이 너무 김
- 분석이 맞지 않음

피드백 이유는 선택사항으로 둔다.

### 4.4 영상 전문성

영상 분석 정확도 개선 자체는 이번 POC 범위가 아니다.
영상 분석 결과는 외부 입력 이벤트로만 받을 수 있게 한다.

```text
VideoAnalysisEvidence
- analysis_id
- observations
- confidence
- source_frame_ids
```

대화 엔진이 영상 분석 결과를 임의로 수정하거나 새로운 영상 관찰을 만들면 안 된다.

## 5. 핵심 원칙

### 5.1 단일 표현 단정 금지

다음 표현만으로 만족도나 감정을 판정하지 않는다.

```text
네
넵
ㅇㅋ
알겠어요
ㅋㅋ
아니
```

예:

```text
입력: "네"
결과: 만족 또는 불만으로 확정하지 않음
참여도 판단: UNKNOWN
확신도: LOW
근거: 단일 확인 표현만 존재
```

`네`와 `넵`의 차이는 사용자 개인의 평소 표현과 대화 흐름이 있을 때만 약한 신호로 사용할 수 있다.

### 5.2 사용자 개인 기준선

사용자별로 다음 기준선을 계산한다.

- 평균 메시지 길이
- 자주 사용하는 확인 표현
- 존댓말 여부
- 질문 빈도
- 추가 설명 빈도
- 영상 업로드 빈도
- 교정 결과 보고 빈도

표본이 부족하면 기준선을 만들지 않는다.
욕설, 짧은 표현, 이모티콘 등을 곧바로 부정 감정으로 분류하지 않는다. 사용자의 평소 스타일과 비교한다.

### 5.3 추정과 사실 분리

다음 항목을 분리한다.

```text
명시적 요청: 사용자가 직접 말한 내용
확인된 사실: 사용자 또는 영상으로 확인된 내용
추정 니즈: 대화 흐름에서 추정한 내용
참여도 추정: 행동 변화에서 추정한 내용
```

모든 추정에는 다음 값이 필요하다.

```text
confidence
evidence_message_ids
reason
last_updated_at
```

근거가 없으면 추정하지 않는다.

### 5.4 추정 결과 수정 가능

새로운 메시지나 행동이 들어오면 기존 추정을 갱신할 수 있어야 한다.
이전 추정 기록은 삭제하지 않고 변경 이력으로 남긴다.

## 6. 입력 스키마

최소 입력은 다음을 포함한다.

```text
ConversationInput
- user_id
- conversation_id
- messages[]
- behavior_events[]
- feedback_events[]
- optional_video_evidence[]
```

Message

```text
- message_id
- role
- text
- created_at
```

BehaviorEvent

```text
- event_id
- event_type
- related_message_id
- created_at
```

이벤트 예:

```text
VIDEO_UPLOADED
RETURNED_TO_CONVERSATION
PRACTICE_RESULT_REPORTED
FOLLOW_UP_QUESTION
TOPIC_REPEATED
```

FeedbackEvent

```text
- feedback_id
- target_message_id
- feedback_type
- optional_reason
- created_at
```

## 7. 출력 스키마

```text
ConversationState
- explicit_intent
- active_coaching_topic
- confirmed_user_facts
- style_baseline
- inferred_needs[]
- engagement_state
- unresolved_open_loops[]
- next_response_strategy
- selected_context_message_ids[]
```

### ExplicitIntent

예상 유형:

```text
CAUSE_EXPLANATION
CORRECTION_ACTION
COMPARISON
DIRECTION_CONFIRMATION
PROGRESS_CHECK
GENERAL_QUESTION
UNKNOWN
```

### InferredNeed

예상 유형:

```text
NEEDS_CERTAINTY
NEEDS_SIMPLER_EXPLANATION
NEEDS_ACTIONABLE_STEP
NEEDS_PROGRESS_RECOGNITION
NEEDS_PROBLEM_REFRAMING
UNKNOWN
```

숨은 니즈는 항상 확신도와 근거를 포함한다.

### EngagementState

```text
level:
- HIGH
- MEDIUM
- LOW
- UNKNOWN

trend:
- INCREASING
- STABLE
- DECREASING
- UNKNOWN
```

### NextResponseStrategy

예:

```text
ANSWER_DIRECTLY
ASK_ONE_CLARIFYING_QUESTION
REDUCE_EXPLANATION_LENGTH
CONNECT_PREVIOUS_COACHING_TOPIC
RECOGNIZE_MEANINGFUL_PROGRESS
OPEN_NEXT_PRACTICE_LOOP
DO_NOT_INFER
```

한 번에 너무 많은 전략을 반환하지 않는다. 주 전략 하나와 선택적 보조 전략 하나까지만 허용한다.

## 8. 필수 테스트 fixture

### Fixture 1 — 단독 `네`

```text
사용자 기준선 없음
마지막 메시지: "네"
```

기대 결과:

```text
engagement_state = UNKNOWN
inferred_need = 없음 또는 UNKNOWN
next_response_strategy = DO_NOT_INFER
```

### Fixture 2 — 단독 `넵`

`넵`이라는 이유만으로 `네`보다 긍정적으로 판정하면 실패다.

### Fixture 3 — 사용자 기준선과 다른 짧은 반응

평소에는 질문과 설명이 길었던 사용자가 연속으로 짧은 답변만 제공한다.

기대 결과:

- 참여도 감소 가능성만 추정
- 불만 또는 이탈로 확정하지 않음
- 근거 메시지 ID 포함
- 확신도 LOW 또는 MEDIUM

### Fixture 4 — 명시적 원인 질문

```text
"자꾸 당겨 치는데 왜 그런 거야?"
```

기대 결과:

```text
explicit_intent = CAUSE_EXPLANATION
```

영상이 없다면 실제 스윙 원인을 확정하지 않는다.

### Fixture 5 — 반복 확인

사용자가 같은 교정 방향을 여러 번 확인한다.

기대 결과:

```text
inferred_need = NEEDS_CERTAINTY 가능
```

단, 반복 질문만으로 불안이나 불신을 확정하지 않는다.

### Fixture 6 — 실제 개선 보고

```text
"말한 대로 해보니까 잘 맞아요."
```

이후 영상 재업로드 또는 연습 결과 이벤트가 존재한다.

기대 결과:

- ProgressEvent로 처리
- 의미 있는 발전 인식 가능
- `RECOGNIZE_MEANINGFUL_PROGRESS`
- 다음 연습과 연결되는 Open Loop 생성 가능

### Fixture 7 — 좋아요와 실제 효과 구분

답변에 `도움 됐어요`만 누른 경우와 `실제로 해보니 좋아짐`을 선택한 경우를 구분한다.
실제 효과 보고를 더 강한 증거로 처리한다.

### Fixture 8 — 사용자의 정정

AI가 `NEEDS_CERTAINTY`로 추정했지만 사용자가 다음 메시지에서 다음과 같이 말한다.

```text
"확신이 필요한 게 아니라 설명이 너무 어려워."
```

기대 결과:

- 기존 추정 갱신
- `NEEDS_SIMPLER_EXPLANATION` 반영
- 이전 추정 이력 보존

### Fixture 9 — 욕설이나 축약 표현

사용자가 평소에도 욕설과 축약 표현을 자주 사용한다.

기대 결과:

- 욕설만으로 부정 감정 판정 금지
- 개인 기준선과 비교

### Fixture 10 — 영상 근거와 사용자 느낌 충돌

사용자는 팔 문제라고 말하지만 영상 분석 결과는 전환 문제를 우선으로 제시한다.

기대 결과:

- 영상 관찰을 분석 근거로 우선 사용
- 사용자 느낌은 니즈와 설명 방식에만 참고
- 새로운 영상 관찰을 채팅 모듈이 만들어내지 않음

## 9. 구현 방식

최소 구조로 구현한다.

권장 구성:

```text
poc/conversation-state-tracker/
├── README.md
├── schemas.py
├── state_tracker.py
├── baseline.py
├── fixtures/
└── tests/
```

조건:

- Python 3.11 기준
- Pydantic v2 사용 가능
- 프로젝트에 없는 패키지를 새로 설치하지 않음
- 가능하면 표준 라이브러리와 기존 의존성 사용
- 공개 함수 타입 힌트 필수
- 원본 메시지와 파생 상태 분리
- 운영 DB 연결 금지
- Supabase 연결 금지
- Java 코드 수정 금지
- 기존 FastAPI 운영 API 수정 금지
- 외부 유료 LLM 호출 금지

LLM 연결이 필요하다면 먼저 Port 인터페이스만 만들고 테스트에서는 mock 또는 fixture를 사용한다. 기존 Gemini 연결을 임의로 호출하지 않는다.

## 10. POC 실행 방식

다음 중 가장 단순한 하나를 선택한다.

- JSON fixture를 읽어 상태 JSON을 출력하는 CLI
- 독립 FastAPI endpoint

추천은 CLI다.

예:

```bash
python main.py --fixture fixtures/acknowledgement_without_baseline.json
```

출력:

```json
{
  "explicit_intent": "UNKNOWN",
  "engagement_state": {
    "level": "UNKNOWN",
    "trend": "UNKNOWN",
    "confidence": "LOW"
  },
  "inferred_needs": [],
  "next_response_strategy": "DO_NOT_INFER"
}
```

## 11. 완료 기준

- 필수 fixture 10개가 존재한다.
- `네`와 `넵`을 단독으로 다르게 감정 판정하지 않는다.
- 모든 추정 결과에 확신도와 근거가 있다.
- 사용자 기준선이 부족하면 `UNKNOWN`을 반환한다.
- 원본 메시지와 파생 상태가 분리된다.
- 사용자 정정으로 기존 추정을 갱신할 수 있다.
- 피드백과 실제 행동 결과를 구분한다.
- 영상 분석 결과를 외부 근거로만 사용한다.
- 기존 운영 코드에는 변경이 없다.
- 테스트와 Ruff 검증 결과를 보고한다.

## 12. 이번 작업에서 하지 말 것

- 실제 운영 코드 통합
- Java/Spring Boot 수정
- 기존 LangGraph 변경
- DB migration
- Supabase 연결
- 음성 또는 억양 분석
- 카메라 기능
- 영상 Pose Estimation 구현
- 사용자 감정 확정
- 외부 API 호출
- Git commit, branch, push

## 13. 완료 보고

다음 형식으로 보고한다.

```text
생성 파일:
- ...

POC에서 확인된 동작:
- ...

통과한 fixture:
- ...

테스트:
- 실행 명령
- 통과/실패 결과

확인하지 못한 것:
- ...

운영 코드 변경:
- 없음

다음 단계 후보:
- POC 결과를 검토한 뒤에만 운영 LangGraph 및 Java 상태 저장 구조와의 통합을 설계
```

---

## 14. 조건부 승인 반영 사항 (2026-08-28)

계획 검토 결과 다음 네 가지를 반영해 구현한다. 아래 내용은 앞 절의 해당 항목보다 우선한다.

### 14.1 근거는 `EvidenceReference`로 일반화한다 (5.3, 6장 보강)

추정 근거를 `evidence_message_ids`로 제한하지 않는다. 메시지, 행동 이벤트, 피드백,
영상 분석 결과를 모두 동등하게 근거로 참조할 수 있어야 한다.

```text
EvidenceReference
- source_type: MESSAGE | BEHAVIOR_EVENT | FEEDBACK_EVENT | VIDEO_ANALYSIS
- source_id
```

모든 추정은 다음을 갖는다.

```text
confidence
evidence: EvidenceReference[]   # 최소 1개. 비면 추정 생성 자체를 거부한다.
reason
last_updated_at
```

`source_id`는 입력에 실재하는 ID여야 한다. 존재하지 않는 ID를 참조하면 실패로 처리한다.

운영 계약(`internal-api.openapi.yaml` 2.0.0)의 `EvidenceReference.source_type`은
`MESSAGE | OBSERVATION | ANALYSIS_EPISODE | PROGRESS_EVENT | ROADMAP_MILESTONE`이다.
POC의 `BEHAVIOR_EVENT`와 `FEEDBACK_EVENT`는 계약에 대응 값이 없는 POC 전용 확장이며,
`VIDEO_ANALYSIS`는 계약의 `ANALYSIS_EPISODE`에 대응한다. 이 매핑은 README에 표로 남기고,
운영 통합 시 계약 변경 여부를 별도로 판단한다.

### 14.2 영상 근거 불변성은 frozen이 아니라 테스트로 보장한다 (4.4, 5.3 보강)

`VideoAnalysisEvidence`의 모델 frozen 설정만으로 "신규 관찰 생성이 차단된다"고 표현하지 않는다.
frozen은 재할당만 막을 뿐 새 관찰 문자열을 만들어내는 것을 막지 못한다.

다음을 명시적 테스트로 검증한다.

1. 트래커 실행 전후로 입력 `video_evidence`의 직렬화 결과가 완전히 동일하다.
2. 출력의 모든 `VIDEO_ANALYSIS` 근거 `source_id`가 입력 `analysis_id` 집합에 포함된다.
3. 영상에서 유래한 `confirmed_user_facts`의 `statement`가 입력 `observations` 문자열과
   글자 단위로 일치한다. 요약, 재작성, 병합, 신규 생성이 모두 실패로 판정된다.

### 14.3 사용자 보고 발전과 영상 확인 발전을 분리한다 (8장 Fixture 6, 7 보강)

`해보니 좋아졌다`는 사용자 보고다. 사용자 보고 전제 위에서 인정할 수 있지만
실제 스윙 개선으로 확정하지 않는다. 영상 비교 근거가 있을 때만 상위 근거 수준으로 올린다.

```text
ProgressAssessment
- level: NONE | USER_REPORTED_PROGRESS | RESULT_REPEATED | VIDEO_VERIFIED_PROGRESS
- swing_improvement_confirmed: bool     # VIDEO_VERIFIED_PROGRESS 에서만 true
- recognition_intensity_cap: ACKNOWLEDGEMENT | SPECIFIC_RECOGNITION | PROGRESS_DECLARATION
- confidence / evidence / reason / last_updated_at
```

| 입력 근거 | level | swing_improvement_confirmed | intensity cap |
|---|---|---|---|
| 사용자 발화 개선 보고 또는 `실제로 해보니 좋아짐` 피드백 | `USER_REPORTED_PROGRESS` | `false` | `ACKNOWLEDGEMENT` |
| 연습 결과 보고가 반복됨 | `RESULT_REPEATED` | `false` | `SPECIFIC_RECOGNITION` |
| 영상 분석이 이전 분석 대비 개선을 제시 | `VIDEO_VERIFIED_PROGRESS` | `true` | `PROGRESS_DECLARATION` |

`RECOGNIZE_MEANINGFUL_PROGRESS` 전략은 `USER_REPORTED_PROGRESS`에서도 선택할 수 있다.
다만 그 경우 `swing_improvement_confirmed`는 `false`이며 인정 강도는 `ACKNOWLEDGEMENT`를 넘지 않는다.
이는 계약 §3.9와 §9.7의 "사용자 체감만으로 영상 개선을 선언하지 않는다"를 따른 것이다.

영상 비교 판정은 대화 엔진이 만들지 않는다. 외부 입력으로만 받는다.
이를 위해 `VideoAnalysisEvidence`에 다음 두 필드를 POC 확장으로 추가한다.

```text
- comparison: IMPROVED | UNCHANGED | REGRESSED | NOT_COMPARED   (기본 NOT_COMPARED)
- compared_to_analysis_id: str | null
```

### 14.4 `네` / `넵` 비교는 의미상 판정으로 한다 (8장 Fixture 2 보강)

전체 출력 JSON을 그대로 비교하지 않는다. 메시지 ID와 시각이 달라 비교가 성립하지 않는다.
다음 의미상 판정 집합이 동일한지 비교한다.

```text
engagement_state.level
engagement_state.trend
engagement_state.confidence
inferred_needs 의 (need_type, confidence) 집합
progress.level
next_response_strategy
secondary_strategy
explicit_intent
```

### 14.5 기준선 최소 표본 (5.2 보강)

기준선 최소 표본 6개는 **POC 가설값이며 실제 사용자 데이터로 검증되지 않았다.**
이 사실을 상수 docstring과 `README.md`에 명시한다. 운영 반영 전에 재조정 대상이다.

### 14.6 작업 공간 경계 재확인

`backend/domain-application`, `backend/ai-processing`을 포함한 기존 운영 코드와
Orca의 Python·Java 작업 공간은 이번 작업에서 읽기만 하고 수정하지 않는다.

---

## 15. 범위 정정 — 단일 짧은 응답 처리의 위치 (2026-08-28)

`네` / `넵` 비교는 **POC 목표, UI 설명, 완료 기준, 대표 시나리오에서 제외한다.**
이 항목은 단일 짧은 응답을 과도하게 해석하지 않는지 확인하는 **내부 회귀 테스트 하나**로만 남긴다.

앞의 1장 목표, 8장 Fixture 1·2, 11장 완료 기준 중 해당 서술은 이 절로 대체된다.

사용자 체험 POC의 중심은 다음이다.

```text
코칭 주제
대화 히스토리
니즈 추정
답변 피드백
발전 상태
Open Loop 추적
```

## 16. 1단계 — 상태 추적기 결함 수정

2026-08-28 검토에서 재현된 8건을 수정한다. 각 항목은 결함을 먼저 재현하는 테스트를 만든 뒤 수정한다.

### 16.1 Topic 기반 컨텍스트 선택 (P0)

추가 필드: `Message.topic_id`, `BehaviorEvent.topic_id`, `FeedbackEvent.topic_id`, `OpenLoopRef.topic_id`.

활성 코칭 주제가 있으면 다음 순서로 선택하고 다른 topic 메시지는 선택하지 않는다.

```text
현재 사용자 메시지
→ active_coaching_topic 과 같은 topic 메시지
→ 해당 topic 의 근거 메시지
→ 최대 12개
```

드라이버·아이언 주제가 섞인 fixture 를 추가하고 활성 주제 전환 시 선택 결과가 달라지는지 검증한다.

### 16.2 Open Loop 처리 (P0)

`OpenLoopRef` 에 `topic_id`, `created_at`, `state: PENDING | FULFILLED | REPLACED | CANCELLED` 를 둔다.
`BehaviorEvent` 에 `open_loop_id: str | None` 을 둔다.

- 이벤트에 연결된 Open Loop 만 처리한다.
- active topic 과 같은 Open Loop 만 처리한다.
- 같은 topic 의 최신 PENDING Open Loop 최대 1개만 대상으로 한다.
- 무관한 영상 업로드나 다른 topic 결과 보고로 종료하지 않는다.
- 입력 객체를 직접 변경하지 않는다.

### 16.3 영상 신뢰도 (P1)

`comparison = IMPROVED` 승격 조건을 모두 만족해야 한다.

```text
compared_to_analysis_id 존재
compared_to_analysis_id != 현재 analysis_id
비교 대상 analysis 가 입력에 존재
confidence 가 MEDIUM 이상
```

LOW confidence 영상만 있으면 `VIDEO_VERIFIED_PROGRESS`, `swing_improvement_confirmed=true`,
결과 `confidence=HIGH` 를 금지한다. LOW confidence 영상은 단독으로 `RESULT_REPEATED` 를 만들지 않는다.
결과 confidence 는 영상 입력 confidence 를 초과하지 않는다.

### 16.4 기준선 상수 분리 (P1)

```text
BASELINE_MIN_HISTORICAL_MESSAGES = 6
BASELINE_RECENT_EXCLUSION = 3
BASELINE_MIN_TOTAL_USER_MESSAGES = 9
```

6·7·8 에서 미생성, 9 부터 생성됨을 경계값으로 직접 검증한다.
세 값 모두 실제 데이터로 검증되지 않은 POC 가설임을 README 에 유지한다.

### 16.5 입력 ID 무결성 (P1)

`ConversationInput` 검증에서 다음을 확인한다. 근거 종류가 다르면 같은 문자열 ID 를 쓸 수 있으므로
**source type 별로** 중복을 검사한다.

- Message / BehaviorEvent / FeedbackEvent / VideoAnalysisEvidence ID 중복 금지
- `related_message_id` 가 있으면 실제 Message 참조
- `target_message_id` 는 실제 assistant Message 참조
- `open_loop_id` 가 있으면 실제 Open Loop 참조
- `compared_to_analysis_id` 는 실제 다른 분석 참조
- prior state 가 현재 대화·topic 과 충돌하지 않음

### 16.6 반복 결과 중복 계산 방지 (P1)

같은 결과에 대한 `PRACTICE_RESULT_REPORTED` 와 `ACTUALLY_IMPROVED` 가 함께 들어와도 한 번으로 센다.
`related_message_id` 와 `target_message_id` 로 anchor 를 맞춰 dedupe 한다.
서로 다른 시점의 결과가 최소 두 번 있어야 `RESULT_REPEATED` 로 승격한다.

### 16.7 추정 이력 (P2)

```text
InferenceRevision
- previous_inference: InferredNeed | null
- new_inference: InferredNeed | null
- trigger_evidence: EvidenceReference[]
- revised_at
- reason
```

삭제, 추가, 1→다, 다→1, 그리고 메시지가 아닌 행동·피드백·영상에 의한 변경을 모두 검증한다.
최신 사용자 메시지를 무조건 trigger 로 쓰지 않는다.

### 16.8 참여도 이벤트 범위 (P2)

참여도에 쓰는 행동 이벤트는 현재 active topic 이며 현재 turn 에 속한 것으로 제한한다.
참여도 근거에 실제 `BehaviorEvent` reference 를 포함한다.

### 16.9 생성 캐시 정리 (P3)

`__pycache__/`, `tests/__pycache__/`, `.ruff_cache/` 만 제거한다.
소스·fixture·사용자 파일은 삭제하거나 이동하지 않는다.

## 17. 2단계 — 사용자가 직접 써보는 로컬 POC

1단계 수정과 검증을 완료한 뒤 **별도의 논리적 변경**으로 진행한다.

### 17.1 확인 목적

이 POC 는 골프 답변 품질을 검증하는 제품이 아니다. 다음을 직접 확인하는 도구다.

- 여러 코칭 주제가 섞여도 현재 주제만 가져오는가
- 사용자 보고와 영상 확인 발전을 구분하는가
- 좋아요와 실제 개선 보고를 구분하는가
- Open Loop 가 해당 코칭 주제에서만 처리되는가
- 어떤 근거로 니즈와 참여도를 추정했는지 확인할 수 있는가

### 17.2 실행 형태

새 패키지를 설치하지 않고 표준 라이브러리 HTTP 서버를 쓴다.

```text
poc/conversation-state-tracker/
├── web_app.py
├── demo_renderer.py
└── web/
    ├── index.html
    ├── app.js
    └── style.css
```

```bash
python web_app.py --host 127.0.0.1 --port 8765
```

### 17.3 화면

채팅 영역: 메시지 입력, 전송, 대화 표시, 현재 코칭 주제 선택, 새 주제 생성, 세션 초기화.

답변 피드백 버튼: `도움 됐어요`, `이해하기 어려워요`, `내 문제와 달라요`,
`실제로 해보니 좋아졌어요`, `답변이 너무 길어요`. 이유 입력은 선택사항.

상태 확인 패널(접기·펼치기): 활성 코칭 주제, 명시적 질문 목적, 추정 니즈와 confidence,
참여도 level·trend·confidence, 사용자 보고/영상 확인 발전 수준, 선택된 응답 전략,
사용된 EvidenceReference, 컨텍스트로 선택된 메시지, 현재 PENDING Open Loop.

### 17.4 POC 답변

외부 LLM 을 연결하지 않는다. 상태 추적 결과를 사람이 읽을 수 있는 짧은 문장으로 바꾸는
결정적 demo renderer 를 만든다. 골프 전문 코칭 결과가 아니라 상태 추적 POC 임을 화면에 표시한다.

### 17.5 저장

운영 DB·Supabase·서버 영구 저장 금지. 브라우저 메모리 또는 `localStorage` 만 사용하고
초기화 버튼으로 전체 삭제할 수 있게 한다.

### 17.6 HTTP

```text
GET  /health
GET  /
POST /api/track   → { conversation_state, demo_reply }
```

잘못된 입력에는 구조화 오류를 반환하고 부분 상태를 반환하지 않는다.

### 17.7 테스트

기존 테스트를 유지하면서 혼합 topic, 무관한 Open Loop 이벤트, LOW confidence 영상,
비교 대상 없는 영상, 기준선 6·7·8·9 경계, 중복 ID, dangling relation,
같은 결과의 행동+피드백 중복, 서로 다른 결과 2회, 추가·삭제·다중 추정 변경 이력,
오래된 행동 이벤트, 다른 topic 행동 이벤트를 추가한다.

HTTP 최소 검증: `GET /health` 200, `GET /` 200, 정상 `POST /api/track` 200,
잘못된 payload 400 또는 422, topic 전환 시 선택 컨텍스트 변경.

서버 시작과 `curl` 검증은 실행 직전 사용자에게 확인받고, 검증 후 임시 서버를 종료한다.

### 17.8 완료 기준

- 재현 8건이 모두 회귀 테스트로 고정됨
- 전체 테스트와 Ruff 통과
- 운영 코드 변경 없음
- 브라우저에서 자유 문장 입력 가능
- topic 을 바꾸면 관련 메시지만 컨텍스트로 선택됨
- 피드백과 실제 효과 보고를 구분함
- 상태 판정의 근거를 화면에서 확인할 수 있음
- 외부 LLM·DB·Supabase 미사용
- Windows 실행 여부와 미검증 사항을 별도 보고
