# Java/Python Backend Boundary Contract

상태: CONFIRMED — 2026-08-26
기계 판독 가능한 원본 계약: `internal-api.openapi.yaml`

## 호출 방향

```text
Client → Java/Spring Boot Domain Application → Python/FastAPI AI Processing Unit
```

- Client는 FastAPI를 직접 호출하지 않는다.
- Spring Boot는 Client-facing API, 제품 DB, 대화와 분석 상태를 소유한다.
- FastAPI는 내부 AI 분석·코칭 API만 제공한다.

## 공개 API 소유권

Java가 기존 공개 API를 인수한다.

| 공개 API | 소유자 | Python 내부 호출 |
|---|---|---|
| `GET /health` | Java | 필요 시 `GET /internal/health` |
| `POST /v1/chat` | Java | `POST /internal/v1/coaching/text` |
| `POST /v1/analyze` | Java | `POST /internal/v1/analyses` |
| `POST /v1/actions/analyze` | Java | `POST /internal/v1/analyses` |
| `GET /v1/actions/openapi.json` | Java | 없음 |
| `GET /v1/history` | Java | 없음 |
| `DELETE /v1/analysis/{run_id}` | Java | 없음 |

Python은 공개 API, 사용자 식별, 권한, 이력 조회, 삭제를 처리하지 않는다.

## 내부 API

- `GET /internal/health`
- `POST /internal/v1/analyses`
- `POST /internal/v1/coaching/text`

요청·응답의 필드, enum, 길이 제한은 `internal-api.openapi.yaml`을 따른다. Java와 Python 테스트는 `fixtures/`의 같은 JSON을 사용한다.

텍스트 코칭 요청에는 최근 assistant 메시지의 `interaction_meta`와 `has_latest_analysis`를 포함한다. 이는 질문·칭찬 반복을 제한하는 대화 정책 입력이며 제품 이력의 소유권은 계속 Java에 있다.

## 데이터 소유권

### Java가 소유한다

- 사용자와 익명 세션
- 대화와 메시지
- SwingSession과 AnalysisRun 제품 상태
- 미디어 메타데이터와 Storage object path
- 분석 이력, 권한, 삭제, 보관 정책
- Client-facing 최종 응답
- 제품 DB migration

### Python이 생성한다

- 질문과 FEEL을 반영하기 전 `VisionObservation`
- 동결된 `BaseAssessment`
- 근거 범위가 검증된 `CoachContent`
- FFmpeg/FFprobe, Gemini, LangGraph 실행 결과

Python은 제품 이력의 원본 시스템이 아니며 Java 소유 제품 테이블을 읽거나 수정하지 않는다.

## 분석 순서

1. 미디어와 촬영 조건만으로 `VisionObservation`을 생성한다.
2. `BaseAssessment`를 확정하고 변경 불가능하게 동결한다.
3. 이후 `user_question`, `user_feel`, `shot_result`, 대화 이력을 후순위 컨텍스트로 반영한다.
4. `CoachContent`를 Java에 반환한다.
5. Java가 `CoachContent`를 사용자용 대화로 렌더링하고 저장한다.

사용자 질문이나 FEEL 때문에 `VisionObservation` 또는 `BaseAssessment`가 바뀌면 계약 위반이다.

## 미디어 전달

- Java가 private Storage object에 대한 짧은 수명의 signed read URL을 생성한다.
- URL은 내부 요청 직전에 생성하며 유효기간은 다운로드와 설정된 분석 timeout보다 길어야 한다.
- Python은 허용된 Storage host의 HTTPS URL만 내려받는다.
- Python은 파일 크기와 content type을 다시 검증하고 임시 파일을 요청 종료 후 제거한다.
- URL, object path, token은 기본 로그에 남기지 않는다.
- Java에서 Python으로 원본 바이너리를 multipart로 다시 전달하지 않는다.

## 호출·timeout·재시도

- Java → Python 호출은 MVP에서 동기 HTTP 방식이다.
- timeout은 Java의 `AI_PROCESSING_TIMEOUT_SECONDS` 환경 설정으로 관리하며 코드에 고정하지 않는다.
- `request_id`는 호출 추적용이고 `analysis_run_id`는 제품 분석 실행 식별자다.
- Java는 이미 처리 중이거나 완료된 `analysis_run_id`를 다시 호출하지 않는다.
- Python은 제품 DB를 갖지 않으므로 네트워크 단절 상황의 exactly-once를 보장하지 않는다.
- 비용 중복을 막기 위해 timeout, 429, 5xx에 대한 자동 재시도는 하지 않는다.
- 재시도 가능한 오류는 사용자 또는 운영자가 명시적으로 새 실행을 요청할 때만 다시 실행한다.

## 인증과 노출

- 분석과 텍스트 코칭 내부 API는 `Authorization: Bearer <server-token>`을 요구한다.
- token은 양쪽 서버 환경 변수로만 주입하고 Git, 응답, 로그에 남기지 않는다.
- `/internal/health`는 인증 없이 상태만 반환할 수 있지만 외부 Gateway에는 노출하지 않는다.
- CORS는 내부 API 보안 수단으로 사용하지 않는다.

## 성공 상태 규칙

- `succeeded`: `observation`, `base_assessment`, `coach_content`가 모두 존재한다.
- `limited`: 제한된 근거라도 위 세 객체가 존재하고 `cannot_determine`에 한계를 기록한다.
- `rejected`: 비골프 미디어이며 `observation.is_golf_media=false`, `base_assessment=null`, `coach_content=null`이다.

## 실패 계약

오류 본문은 `code`, `message`, `retryable`, `request_id`, 선택적인 `analysis_run_id`를 가진다.

| HTTP | code | 의미 |
|---|---|---|
| 401 | `INTERNAL_AUTH_FAILED` | 내부 인증 실패 |
| 415 | `MEDIA_TYPE_UNSUPPORTED` | 지원하지 않는 형식 |
| 422 | `MEDIA_UNAVAILABLE` | signed URL 접근 또는 다운로드 실패 |
| 422 | `MEDIA_DECODE_FAILED` | 파일 또는 프레임 해석 실패 |
| 422 | `ANALYSIS_CONTRACT_FAILED` | 분석 근거 계약 위반 |
| 429 | `MODEL_RATE_LIMITED` | Provider rate limit |
| 502 | `MODEL_UNAVAILABLE` | Provider 호출 실패 |
| 504 | `MODEL_TIMEOUT` | Provider 처리 시간 초과 |
| 500 | `INTERNAL_ERROR` | 분류되지 않은 내부 오류 |

원본 Provider 오류와 시크릿은 사용자 응답에 포함하지 않는다.

## DB 이전 규칙

1. Java가 기존 제품 테이블을 읽고 쓰는 Repository와 migration 소유권을 준비한다.
2. API별 전환 시점 전까지 기존 Python Repository를 유지한다.
3. 하나의 제품 데이터에는 Java 또는 Python 중 한쪽만 쓰는 single-writer 원칙을 지킨다.
4. Java 쓰기 경로의 통합 검증이 끝난 뒤 해당 Python 쓰기 경로를 제거한다.
5. 최종 전환 후 Python에서 SQLAlchemy, Alembic, 제품 DB 설정을 제거한다.

## 변경·검증

- 계약문서 변경, Python 이동, Java 생성, 내부 API 구현, DB 이전, 공개 API 전환을 별도 task로 진행한다.
- 계약 변경 시 OpenAPI와 모든 fixture를 같은 task에서 갱신한다.
- Java와 Python은 같은 fixture로 contract test를 실행한다.
- 양쪽 단위 테스트 후 Java 공개 API에서 Python 내부 API까지 `curl`로 검증한다.
- Provider E2E 실행 여부와 비용 발생 여부를 결과에 명시한다.
