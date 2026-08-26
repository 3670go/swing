# 스윙분석기 현행 프로젝트 문서와 개편 목표

## 1. 현재 프로젝트 요약

`스윙분석기`는 개인 골프 스윙 분석 MVP를 만들기 위한 프로젝트다. 현재 저장소는 백엔드 API와 모바일 UI 프로토타입으로 나뉘어 있다.

- `backend/`: 개인 골프 스윙 분석 API 서버
- `ui-prototype/`: 모바일 골프 스윙 분석 UX 프로토타입

현 단계의 핵심은 “사용자가 골프 스윙 관련 질문과 사진/영상을 제공하면, 시스템이 근거를 분리해 분석하고 대화형 답변을 제공하는 MVP”를 검증하는 것이다.

## 2. 현행 구조

### Backend

`backend/`는 FastAPI 기반 서버다. 주요 책임은 다음과 같다.

- 텍스트 기반 골프 스윙 코칭 대화
- 사진/영상 업로드 기반 분석 실행
- 분석 이력 조회와 삭제
- Supabase DB/Storage 연동
- Gemini 기반 구조화 응답 생성
- Custom GPT Action 연동

주요 기술 구성:

- Python `>=3.11,<3.12`
- FastAPI
- LangGraph
- Google GenAI/Gemini
- SQLAlchemy / Alembic
- Supabase
- Uvicorn

주요 endpoint:

- `GET /health`
- `POST /v1/chat`
- `POST /v1/analyze`
- `POST /v1/actions/analyze`
- `GET /v1/actions/openapi.json`
- `GET /v1/history`
- `DELETE /v1/analysis/{run_id}`

확인된 검증 상태:

- `python -m unittest discover -s tests -q`: 50개 테스트 통과
- `python -m ruff check .`: 통과
- HTTP smoke test에서 경량 API, validation, auth gate, delete not-found, 격리 서버 기준 `/v1/chat` E2E 200 확인
- 기존 `127.0.0.1:8000` 서버에서 `/v1/chat` 502가 한 번 있었고, Gemini 429 retry 로그가 관찰됨

### UI Prototype

`ui-prototype/`은 React/Vite 기반 모바일 UX 프로토타입이다. 실제 제품 앱 전체가 아니라, 모바일 디바이스 프레임 안에서 핵심 사용자 흐름을 검증하는 목적이다.

주요 책임:

- 채팅 중심 스윙 분석 UX 검증
- 사진/영상 첨부 후 분석 draft 검토 흐름
- 분석 시작 전 컨텍스트 확인
- iPhone/Pixel 프레임, safe area, keyboard runtime 기반 모바일 상호작용 확인

주요 기술 구성:

- React 19
- Vite
- TypeScript
- Playwright

확인된 검증 명령:

- `npm run check:runtime`
- `npm run build`
- `npm run test:runtime`
- `npm run test:sites`

## 3. 현재 문서 상태

현재 작성된 문서는 다음과 같다.

- `README.md`: 프로젝트 전체 요약과 실행 진입점
- `backend/README.md`: 백엔드 목적, 구조, 설정, 실행, 검증
- `ui-prototype/README.md`: UI 프로토타입 목적, 구조, 실행, 검증, 작업 경계
- `AGENTS.md`: 현재 운영 지침 파일. 사용자가 프로젝트에 맞게 교체할 예정
- `ui-prototype/AGENTS.md`: 모바일 프로토타입 runtime과 protected 파일 경계 지침

주의:

- `AGENTS.md`는 이번 개편에서 교체 예정이므로, 현행 내용은 참고하되 새 기준 문서로 재정렬할 필요가 있다.
- `.env`, `.youtube_api_key` 등 실제 시크릿 값은 문서화하지 않는다.

## 4. 현행 제품 판단 체계

현재 프로젝트의 중요한 분석 원칙은 다음과 같다.

- 사용자의 체감 표현은 `FEEL`로 보존한다.
- 영상에서 직접 확인되는 움직임은 `OBSERVATION`으로 분리한다.
- 센서나 런치모니터 수치는 `MEASUREMENT`로 분리한다.
- `FEEL`, `OBSERVATION`, `MEASUREMENT`를 근거 없이 섞지 않는다.
- 2D 영상만으로 Club Path, Face Angle, Face-to-Path, Attack Angle, Low Point, Ground Reaction Force 같은 측정값을 확정하지 않는다.
- 사진은 단일 프레임 근거로만 제한적으로 사용한다.
- 비골프 미디어는 명시적으로 rejected state를 가져야 한다.
- 사용자 질문과 FEEL은 답변 맥락이며, 영상 관찰과 기본 판정이 먼저 고정되어야 한다.

이 원칙은 프로젝트 개편 후에도 유지해야 할 핵심 도메인 계약이다.

## 5. 개편 목표

### 목표 1: 프로젝트 기준 문서 재정비

`AGENTS.md`를 현재 프로젝트 상태에 맞게 교체한다.

새 `AGENTS.md`는 다음을 명확히 해야 한다.

- 프로젝트 목적
- 작업 범위
- 백엔드와 UI 프로토타입의 역할
- 시크릿/원본 데이터 보호 규칙
- 골프 스윙 분석 용어와 근거 분리 규칙
- 테스트와 검증 기준
- protected runtime 수정 경계
- Git 작업 금지/허용 조건

### 목표 2: 백엔드 API 계약 안정화

현재 API가 MVP 흐름을 안정적으로 지원하는지 확인하고, 외부 provider 영향과 코드 결함을 분리할 수 있게 만든다.

우선순위:

- `/v1/chat`의 provider 429/503 retry와 실패 응답 기준 정리
- `/v1/analyze` 실제 이미지/영상 E2E 검증
- `/v1/actions/analyze` 인증 성공 케이스 검증
- 분석 이력 생성, 조회, 삭제까지 한 흐름으로 검증
- API request/response 예시를 문서화

### 목표 3: UI 프로토타입과 백엔드 연결 검증

UI가 백엔드의 실제 API 계약과 맞는지 확인한다.

우선순위:

- `VITE_API_BASE_URL` 기준 로컬 백엔드 연결 확인
- 채팅 전송 흐름 확인
- 사진/영상 첨부 draft 흐름 확인
- 분석 시작, 결과 표시, 실패 상태 표시 확인
- 비골프 미디어 rejected state 표시 확인

### 목표 4: 테스트 체계 분리

테스트를 목적별로 분리한다.

- 단위 테스트: 빠르게 반복 가능한 로직 검증
- API smoke test: routing, validation, auth gate, health, history 확인
- Provider E2E: Gemini/Supabase가 실제로 붙는 비용 있는 검증
- UI runtime test: protected mobile runtime 보존 확인
- UI integration test: 백엔드 연결 흐름 확인

### 목표 5: MVP 범위 고정

개편 전에 MVP에 들어갈 것과 들어가지 않을 것을 분리한다.

MVP에 필요한 것:

- 텍스트 질문 기반 코칭
- 사진/영상 업로드 기반 분석
- 분석 결과와 대화 이력 저장
- 분석 근거 분리
- 사용자 FEEL과 관찰의 일치/불일치 설명
- 한 번에 하나의 다음 실험 제안

MVP에서 아직 확정하지 않을 것:

- 2D 영상만으로 측정값을 확정하는 기능
- 실시간 카메라 분석
- 스윙 데이터 기반 수치 예측
- 전체 회원/결제/권한 체계
- 대규모 소셜/커뮤니티 기능

## 6. 개편 작업 순서 제안

1. 새 `AGENTS.md` 초안 작성
2. 백엔드 API 계약 문서 보강
3. `/v1/analyze` 실제 미디어 E2E 테스트
4. UI와 백엔드 연결 흐름 테스트
5. 실패 상태와 사용자 메시지 정책 정리
6. MVP 범위 문서 확정
7. 이후 코드 구조 개편 여부 판단

## 7. 현재 리스크와 확인 필요 사항

확인된 리스크:

- Gemini provider의 429/503이 실제로 발생할 수 있다.
- 기존 8000 서버와 격리 서버의 `/v1/chat` 결과가 달랐던 적이 있어, 서버 프로세스 상태와 외부 provider 상태를 분리해서 봐야 한다.
- 실제 `/v1/analyze` 성공 케이스는 아직 확인하지 않았다.
- 실제 `/v1/actions/analyze` 인증 성공 케이스는 아직 확인하지 않았다.
- UI와 백엔드의 실제 통합 흐름은 아직 확인하지 않았다.

확인 필요:

- 테스트용 골프 이미지/영상 샘플
- Supabase Storage bucket과 DB migration 적용 상태
- Custom GPT Action에서 사용할 실제 배포 URL 또는 로컬 테스트 방식
- UI에서 기대하는 실패 메시지와 재시도 UX

## 8. 다음 액션

가장 먼저 할 일은 `AGENTS.md`를 현행 프로젝트 기준으로 다시 작성하는 것이다. 그 다음 백엔드 E2E, UI 통합 검증, MVP 범위 고정을 순서대로 진행한다.

추천 순서:

1. `AGENTS.md` 교체안 작성
2. 실제 미디어 1개로 `/v1/analyze` E2E 확인
3. UI에서 채팅과 분석 요청을 백엔드에 붙여 확인
4. 실패 케이스와 재시도 정책 문서화
5. MVP에 포함할 기능과 제외할 기능 확정

## 백엔드 책임분리 설계 결정

### 결정

백엔드는 Java/Spring Boot Domain Application과 Python/FastAPI AI Processing Unit으로 분리한다.

Client는 Spring Boot를 호출하고, Spring Boot가 FastAPI 분석 서버를 내부 호출한다.

### Java/Spring Boot에 둘 책임

- Client-facing API
- 사용자/익명 세션/로그인
- 대화/메시지/분석 이력
- 분석 상태 관리
- 제품 DB 소유
- 권한/삭제/보관 정책
- FastAPI 내부 호출
- 사용자에게 반환할 최종 응답 조립

### Python/FastAPI에 남길 책임

- AI Processing Unit
- 영상/사진 분석 처리
- FFmpeg/FFprobe 프레임 추출
- LangGraph 분석 파이프라인
- Gemini API 호출
- FEEL/OBSERVATION/MEASUREMENT 분석 규약 실행
- VisionObservation / BaseAssessment / CoachContent 생성
- 분석 결과를 Spring Boot에 반환

### 진행 순서

1. 현재 FastAPI 내부 책임분리를 먼저 진행한다.
2. UseCase / Domain Policy / Port / Adapter 경계를 만든다.
3. Spring Boot가 가져갈 Domain Application 책임을 문서화한다.
4. 이후 Java/Spring Boot와 Python/FastAPI를 물리적으로 분리한다.

### 금지 사항

- 책임분리와 기능변경을 동시에 하지 않는다.
- Java/Spring Boot 서버 생성과 FastAPI 책임분리를 동시에 하지 않는다.
- API 동작 변경 없이 구조적 책임분리부터 진행한다.

## backend → api-architecture-refactor → responsibility-separation

### 변경 내용 — 2026-08-26

구조 변경과 기능 변경을 분리해 순차 적용했다.

구조 변경:

- `/v1/analyze` 오케스트레이션을 `StartSwingAnalysisUseCase`로 이동했다.
- 업로드 분류, 임시 저장, 크기 제한, SHA-256 계산을 `UploadedMediaPreparer`로 분리했다.
- FFmpeg 프레임 추출을 `FrameExtractor` Port와 `FfmpegFrameExtractor` Adapter로 분리했다.
- LangGraph 실행을 `AiSwingAnalyzer` Port와 `LangGraphSwingAnalyzer` Adapter로 분리했다.
- 영상 근거 제한, BaseAssessment 생성·동결, CoachContent 검증을 Domain Policy로 이동했다.
- `ChatRuntimeRepository`를 사용자·대화, 메시지, 스윙 분석 Repository로 분리했다.
- 분석 실패를 `AnalysisFailurePolicy`로 통합하고 API 계층에서 HTTP 상태로 변환하도록 변경했다.
- API DTO와 분석 Domain Model을 분리했다.
- 분석 실행 상태 전이를 `AnalysisStatusPolicy`로 분리했다.

별도 기능 변경:

- 사용자 질문은 `user_question`에만 저장하고 `user_feel`에 자동 복사하지 않도록 변경했다.

### 테스트 내용 — 2026-08-26

- `python -m ruff check --fix app tests`: 통과
- `python -m ruff format app tests`: 변경 없음
- `python -m ruff check .`: 통과
- `python -m unittest discover -s tests -q`: 50개 통과
- Fake Adapter 기반 `StartSwingAnalysisUseCase` 정상 사진 분석 경로: 통과
- `curl GET /health`: HTTP 200
- `curl POST /v1/analyze` 미지원 미디어: HTTP 415, `MEDIA_TYPE_UNSUPPORTED`
- `curl POST /v1/analyze` 빈 이미지: HTTP 422, `MEDIA_EMPTY`

검증 공백:

- 실제 Supabase DB·Storage와 Gemini를 사용하는 유료 `/v1/analyze` 성공 경로는 실행하지 않았다.
- 실제 미디어 Provider E2E는 별도 비용 테스트 단계로 남아 있다.

## backend → java-python-split → contract-freeze

### 확정 내용 — 2026-08-26

- Client-facing API와 제품 DB는 Java/Spring Boot가 소유한다.
- Python/FastAPI는 내부 미디어 분석과 텍스트 코칭만 제공한다.
- 공개 API별 Java 소유권과 Python 내부 호출 경로를 확정했다.
- 내부 API는 동기 HTTP, 서버 전용 Bearer token, signed read URL 전달 방식으로 확정했다.
- 모델 비용 중복을 막기 위해 timeout·429·5xx 자동 재시도를 하지 않는다.
- 제품 데이터는 단계별 single-writer 원칙으로 Java에 이전한다.
- Java 기준은 Java 21, Spring Boot 4.1.1, Gradle Kotlin DSL로 확정했다.
- Spring Boot 4.1.1은 2026-08-26 확인 당시 공식 최신 stable이며 Java 17~26을 지원한다. 출처: `https://docs.spring.io/spring-boot/system-requirements.html`

### 계약 파일

- `backend/contracts/java-package-structure.md`
- `backend/contracts/python-package-structure.md`
- `backend/contracts/java-python-boundary.md`
- `backend/contracts/internal-api.openapi.yaml`
- `backend/contracts/fixtures/`

### 다음 분리 순서

1. 계약문서 기준 커밋 — 완료 (`d728dc4`)
2. 기존 Python 코드를 `backend/ai-processing`으로 이동 — 완료 (`80d2de1`)
3. Java/Spring Boot 프로젝트 생성 — 완료
4. Java/Python 내부 API 구현
5. 제품 DB 소유권 이전
6. Client-facing API Java 전환

### Java 골격 검증 — 2026-08-26

- Java 21 toolchain 자동 다운로드 및 사용 확인
- `gradlew.bat test --no-daemon`: 통과
- `gradlew.bat bootRun --no-daemon --args="--server.port=18080"`: 기동 확인
- `curl GET /actuator/health`: HTTP 200, `UP`
- 공개 `/v1/*` API와 DB 기능은 아직 추가하지 않았다.

### 내부 채팅 계약 보정 — 2026-08-26

- 기존 대화 정책 재현에 필요한 `HistoryMessage.interaction_meta`를 내부 계약에 추가했다.
- 최근 분석 존재 여부를 전달하는 `has_latest_analysis`를 텍스트 코칭 요청에 추가했다.
- 제품 이력은 Java가 소유하고 Python은 전달받은 값으로 대화 정책만 계산한다.

### LangGraph content/surface 구조 분리 — 2026-08-26

- 텍스트 코칭 내용을 생성하는 `build_text_content_graph`를 사용자 문장 작성 단계와 분리했다.
- 영상 관찰·기본 판정·코칭 내용을 생성하는 `build_analysis_content_graph`를 사용자 문장 작성 단계와 분리했다.
- 기존 공개 API 그래프는 content graph 뒤에 기존 surface writer를 연결해 응답 동작을 유지한다.
- 내부 API는 content graph에서 종료할 수 있어 Java의 최종 문장 조립 책임과 충돌하지 않는다.
- `ruff check --fix`, `ruff format`, `ruff check`: 통과
- `unittest`: 52개 통과
- `curl GET /health`: HTTP 200
- `curl POST /v1/analyze` 미지원 미디어: HTTP 415

### Python 내부 API 구현 — 2026-08-26

- `GET /internal/health`를 추가했다.
- `POST /internal/v1/analyses`에 Bearer 인증, signed URL host 제한, 크기·SHA-256 검증, 임시 프레임 처리를 추가했다.
- `POST /internal/v1/coaching/text`는 텍스트 `CoachContent`까지만 반환한다.
- 내부 분석·코칭은 Gemini 자동 재시도 없이 한 번만 호출한다.
- 기존 공개 `/v1/*` API와 제품 DB 코드는 전환 완료 전까지 유지한다.
- `ruff check --fix`, `ruff format`, `ruff check`: 통과
- `unittest`: 58개 통과
- `curl GET /internal/health`: HTTP 200
- `curl` 인증 없음: HTTP 401, `INTERNAL_AUTH_FAILED`
- `curl` 잘못된 내부 요청: HTTP 422, `ANALYSIS_CONTRACT_FAILED`
- `curl` 허용되지 않은 미디어 host: HTTP 422, `MEDIA_UNAVAILABLE`
- 실제 Gemini/Supabase Provider E2E는 실행하지 않았다.

