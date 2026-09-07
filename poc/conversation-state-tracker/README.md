# Conversation State Tracker POC

대화 상태 추적 및 사용자 니즈 추론 POC.

작업지시서: `docs/backend/plan/conversation-intelligence/task/conversation-state-tracker-poc.md`

## 이 POC 가 답하려는 질문

`네`, `넵`, `ㅇㅋ` 같은 짧은 답변을 단독으로 해석하지 않고,
사용자 기준선과 앞뒤 대화 및 행동을 이용해 다음 대화 전략을 선택할 수 있는가?

## 범위

- LLM 호출 없음. 전부 결정적 규칙이다. `ports.py` 는 Port 선언만 있고 구현체가 없다.
- 운영 코드(`backend/**`)를 import 하지 않는다. DB, Supabase, 외부 API 연결 없음.
- 영상 분석은 하지 않는다. 외부 입력으로 받은 결과만 읽는다.
- 사용자 감정을 확정하지 않는다. 출력 스키마에 감정 필드가 없다.

## 실행

### 브라우저에서 직접 써보기

```bash
cd poc/conversation-state-tracker
python web_app.py --host 127.0.0.1 --port 8765
# http://127.0.0.1:8765
```

서버에는 아무것도 저장하지 않는다. 대화는 브라우저 `localStorage` 에만 남고
`세션 초기화` 버튼으로 전부 지운다. 외부 LLM·DB·Supabase 를 연결하지 않는다.

화면 왼쪽은 채팅(주제 선택, 새 주제, 초기화, 답변 피드백 버튼, 입력 시뮬레이터),
오른쪽은 상태 확인 패널이다. 패널에서 다음을 접고 펼쳐 확인한다.

```text
활성 코칭 주제 / 명시적 질문 목적 / 추정 니즈와 confidence
참여도 level·trend·confidence / 사용자 보고·영상 확인 발전 수준
응답 전략 / 사용된 EvidenceReference / 컨텍스트로 선택된 메시지
PENDING Open Loop / 추정 변경 이력
```

`입력 시뮬레이터` 에서 행동 이벤트, Open Loop, 영상 분석 결과를 직접 넣을 수 있다.
영상 관찰과 비교 판정은 여기서 넣은 값만 근거가 된다. 대화 엔진이 만들지 않는다.

답변은 `demo_renderer.py` 가 상태에서 결정적으로 만든 설명 문장이다.
골프 코칭 결과가 아니며 화면 상단에 그렇게 표시한다.

### CLI 와 검증

```bash
cd poc/conversation-state-tracker

# 요약 출력
python main.py --fixture fixtures/01_acknowledgement_without_baseline.json

# 전체 상태 출력
python main.py --fixture fixtures/06b_video_verified_progress.json --full

# 테스트
python -m unittest discover -s tests -t .

# 린트
ruff check .
ruff format --check .
```

종료 코드: `0` 정상, `1` 트래커 실패(`TrackerError`), `2` 입력 스키마 위반.

## 파일

| 파일 | 책임 |
|---|---|
| `schemas.py` | 입출력 모델과 enum, 실패 예외. 원본과 파생 상태를 타입으로 분리 |
| `baseline.py` | 사용자 표현 기준선. 표본 부족 시 `None` |
| `signals.py` | 명시적 의도, 발전 근거 수준, 니즈 신호 추출 |
| `state_tracker.py` | `ConversationState` 조립, 근거 검증, 변경 이력 |
| `strategy.py` | 응답 전략 사다리 (주 1 + 보조 최대 1) |
| `ports.py` | LLM Port 선언만. 구현·호출 없음 |
| `main.py` | fixture → 상태 JSON CLI |
| `demo_renderer.py` | 상태 → 사람이 읽는 설명 문장 (결정적, LLM 없음) |
| `web_app.py` | 표준 라이브러리 HTTP 서버. `GET /health`, `GET /`, `POST /api/track` |
| `web/index.html`, `web/app.js`, `web/style.css` | 체험 화면. 상태는 localStorage 에만 |

## 핵심 규칙

### 1. 활성 코칭 주제 밖은 보지 않는다

활성 주제가 있으면 `signals.build_scope` 가 그 주제의 메시지·행동 이벤트·피드백만 남긴다.
컨텍스트 선택은 다음 순서다.

```text
현재 사용자 메시지
→ 같은 topic 메시지
→ 해당 topic 의 근거 메시지
→ 최대 12개(계약 §9.4)
```

주제를 바꾸면 선택되는 메시지가 달라진다
(`RegressionP0TopicScopedContext.test_switching_topic_changes_selected_context`).

참고: 단일 짧은 응답(`네` 등)을 과도하게 해석하지 않는지는
`ShortReplyOverInterpretation` **내부 회귀 테스트 한 곳**에서만 검증한다.
POC 의 목표나 화면의 주제가 아니다.

### 2. 근거는 `EvidenceReference` 로 일반화한다

```python
EvidenceReference(source_type=EvidenceSourceType.BEHAVIOR_EVENT, source_id="b1")
```

| POC `source_type` | 운영 계약(`internal-api.openapi.yaml` 2.0.0) 대응 |
|---|---|
| `MESSAGE` | `MESSAGE` |
| `VIDEO_ANALYSIS` | `ANALYSIS_EPISODE` |
| `BEHAVIOR_EVENT` | 대응 값 없음 (POC 전용 확장) |
| `FEEDBACK_EVENT` | 대응 값 없음 (POC 전용 확장) |

모든 추정은 `Inference` 를 상속해 `confidence`, `evidence`(최소 1개), `reason`,
`last_updated_at` 을 갖는다. 근거가 비면 `InferenceWithoutEvidenceError`,
입력에 없는 ID 를 참조하면 `DanglingReferenceError` 로 실패한다.

### 3. 영상 근거는 읽기만 한다

`VideoAnalysisEvidence` 는 frozen 이지만, **frozen 이 보증하는 것은 재할당 차단뿐이다.**
새 관찰 문자열을 만들어내는 것은 frozen 으로 막히지 않는다. 그래서 테스트로 검증한다.

- `test_input_video_evidence_is_unchanged` — 실행 전후 직렬화 결과 동일
- `test_only_existing_analysis_ids_are_referenced` — 참조 ID 가 입력 집합 안에 있음
- `test_no_new_observation_text_is_produced` — 영상 유래 `statement` 가 입력 `observations`
  와 글자 단위로 일치. 요약·재작성·병합·신규 생성이 전부 실패로 판정된다

`track()` 자체도 실행 후 입력이 바뀌었으면 `VideoEvidenceMutationError` 를 던진다.

### 4. 사용자 보고 발전과 영상 확인 발전을 구분한다

| 입력 근거 | `level` | `swing_improvement_confirmed` | `recognition_intensity_cap` |
|---|---|---|---|
| 사용자 개선 보고, `실제로 해보니 좋아짐` 피드백 | `USER_REPORTED_PROGRESS` | `false` | `ACKNOWLEDGEMENT` |
| 연습 결과 보고 반복 | `RESULT_REPEATED` | `false` | `SPECIFIC_RECOGNITION` |
| 외부 영상 분석의 `comparison = IMPROVED` | `VIDEO_VERIFIED_PROGRESS` | `true` | `PROGRESS_DECLARATION` |

`해보니 좋아졌다` 는 사용자 보고 전제 위에서 인정할 수 있다.
`RECOGNIZE_MEANINGFUL_PROGRESS` 전략은 선택되지만 `swing_improvement_confirmed` 는 `false`,
인정 강도는 `ACKNOWLEDGEMENT` 를 넘지 않는다.
계약 §3.9, §9.7 의 "사용자 체감만으로 영상 개선을 선언하지 않는다"를 따른 것이다.

영상 비교 판정은 대화 엔진이 만들지 않는다. `VideoAnalysisEvidence.comparison` 으로
외부에서만 들어온다.

### 5. 추정은 갱신하고 이력은 남긴다

`ConversationInput.prior_state` 로 이전 상태를 받으면, 니즈가 달라진 경우
`ConversationState.inference_history` 에 `InferenceRevision` 을 추가한다.
이전 값은 지우지 않는다.

## POC 가설값 (검증되지 않음)

아래 상수는 **실제 사용자 데이터로 검증되지 않은 POC 가설값이다.**
운영 반영 전에 실사용 로그로 재조정해야 한다.

| 상수 | 값 | 근거 |
|---|---|---|
| `baseline.BASELINE_MIN_HISTORICAL_MESSAGES` | `6` | 계약 §9.4 의 "최근 메시지 최대 12개"의 절반을 임의로 취함 |
| `baseline.BASELINE_RECENT_EXCLUSION` | `3` | 최근 반응 변화를 탐지하려면 기준선이 오염되면 안 된다는 판단 |
| `baseline.BASELINE_MIN_TOTAL_USER_MESSAGES` | `9` | 위 둘의 합. **기준선이 실제로 생성되는 경계는 6이 아니라 9다** |
| `baseline.SHORT_REPLY_RATIO` | `0.4` | 근거 없음. 임의값 |
| `baseline.is_habitual_profanity` 임계 | `0.3` | 근거 없음. 임의값 |
| 짧은 반응 연속 임계 | `2회`(가능성), `3회`(LOW) | 근거 없음. 임의값 |
| `signals.VIDEO_MIN_PROMOTION_CONFIDENCE` | `MEDIUM` | LOW 신뢰도 영상으로 개선을 확정하지 않기 위한 최소선 |

`state_tracker.MAX_CONTEXT_MESSAGES = 12` 만 계약 §9.4 의 확정 수치를 따른다.

## Fixture

| 파일 | 검증 대상 |
|---|---|
| `01_acknowledgement_without_baseline.json` | 기준선 없는 단독 `네` → `DO_NOT_INFER` |
| `02_acknowledgement_variant_neb.json` | `넵` 의 의미상 판정이 `네` 와 동일 |
| `03_short_replies_against_baseline.json` | 참여도 감소 *가능성*만. 불만·이탈 확정 금지 |
| `04_explicit_cause_question.json` | `CAUSE_EXPLANATION`, 영상 없으면 원인 미확정 |
| `05_repeated_direction_confirmation.json` | `NEEDS_CERTAINTY` 는 LOW 확신도까지만 |
| `06_practice_result_improved.json` | 사용자 보고 발전, `swing_improvement_confirmed=false` |
| `06b_video_verified_progress.json` | 영상 비교가 있을 때만 상위 근거 수준 |
| `07_feedback_actual_effect.json` | `실제로 해보니 좋아짐` = 결과 보고 |
| `07b_feedback_helpful_only.json` | `도움 됐어요` 만으로는 발전 아님 |
| `08_user_correction_of_inference.json` | 정정으로 추정 갱신 + 이력 보존 |
| `09_profanity_within_baseline.json` | 습관적 욕설을 부정 감정으로 보지 않음 |
| `10_video_evidence_conflicts_with_feel.json` | 영상 관찰 우선, FEEL 은 니즈에만 반영 |

`11`~`18` 은 2026-08-28 검토 재현 8건을 고정하는 회귀 fixture다.

| 파일 | 고정하는 결함 |
|---|---|
| `11_mixed_topics.json` | P0 활성 주제와 무관하게 마지막 12개를 선택하던 문제 |
| `12_open_loop_unrelated_event.json` | P0 무관한 이벤트 하나로 모든 Open Loop 가 종료되던 문제 |
| `13_low_confidence_video.json` | P1 LOW 신뢰도 영상이 개선 확정으로 승격되던 문제 |
| `14_video_without_comparison_target.json` | P1 비교 대상 없는 영상이 승격되던 문제 |
| `15_duplicate_result_reports.json` | P1 같은 결과를 두 번 세던 문제 |
| `16_two_distinct_results.json` | 서로 다른 시점의 결과 2회만 `RESULT_REPEATED` |
| `17_stale_behavior_event.json` | P2 오래된 이벤트가 참여도를 HIGH 로 만들던 문제 |
| `18_other_topic_behavior_event.json` | P2 다른 주제 이벤트가 참여도 근거가 되던 문제 |

기준선 경계(6·7·8·9), 중복 ID, dangling relation, 추정 이력 변경은 fixture 없이
`tests/test_state_tracker.py` 안에서 payload 를 직접 구성해 검증한다.

## 하지 않은 것

- 운영 LangGraph, Java Chat Engine, DB 스키마와의 통합
- 실제 LLM 을 이용한 한국어 의도 분류. `signals.detect_explicit_intent` 는
  키워드 규칙이라 fixture 수준 문장만 커버한다
- 계약의 `MILESTONE_COMPLETED` 근거 수준. milestone 과 완료 조건 입력이 없어 범위 밖이다
- 유튜브 댓글 등 외부 사전 데이터 수집

## 요구 환경

- Python 3.11 이상. `schemas.py` 가 `enum.StrEnum` 을 쓰므로 3.10 에서는 동작하지 않는다.
- `pydantic` v2 (`backend/ai-processing/requirements.lock` 의 `pydantic==2.13.4` 기준).
  새로 설치하는 패키지는 없다.
- 테스트는 `unittest` 다. 기존 `backend/ai-processing/tests` 와 같은 방식이며 pytest 를 쓰지 않는다.
- `ruff.toml` 은 `backend/ai-processing/pyproject.toml` 의 `[tool.ruff]` 설정을 복제한 것이다.
  POC 가 그 프로젝트 밖에 있어 설정이 상속되지 않는다.

### 검증한 환경

`Python 3.11.15` + `pydantic 2.13.4` + `ruff 0.16.5` 에서 27개 테스트 통과,
`ruff check` 및 `ruff format --check` 통과를 확인했다.
Windows 로컬 인터프리터에서의 실행은 별도로 확인해야 한다.

## HTTP 계약

| 경로 | 응답 |
|---|---|
| `GET /health` | `200 {"status":"ok"}` |
| `GET /` `/app.js` `/style.css` | `200` 정적 파일. 그 외 경로는 `404` |
| `POST /api/track` | `200 {conversation_state, demo_reply}` |

오류는 구조화해서 돌려주고 **부분 상태를 절대 포함하지 않는다.**

| 상황 | 상태 코드 | `error.code` |
|---|---|---|
| 본문이 비었거나 JSON 이 깨짐 | `400` | `empty_body` / `invalid_json` |
| 입력 스키마 위반 | `422` | `validation_error` |
| ID 무결성 위반 | `422` | `input_integrity_error` |
| 그 외 트래커 실패 | `422` | `tracker_error` |

## 이 POC 로 확인할 수 있는 것

| 확인 항목 | 화면에서 보는 법 |
|---|---|
| 여러 주제가 섞여도 현재 주제만 가져오는가 | 주제를 바꾸고 `컨텍스트로 선택된 메시지` 를 비교 |
| 사용자 보고와 영상 확인 발전을 구분하는가 | `발전 상태` 의 `영상으로 확인됨` 과 `인정 강도 상한` |
| 좋아요와 실제 개선 보고를 구분하는가 | `도움 됐어요` 와 `실제로 해보니 좋아졌어요` 를 각각 눌러 비교 |
| Open Loop 가 해당 주제에서만 처리되는가 | 다른 주제에서 이벤트를 넣고 `PENDING Open Loop` 확인 |
| 어떤 근거로 추정했는가 | 각 항목의 `EvidenceReference` 태그와 이유 문장 |
