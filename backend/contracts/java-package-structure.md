# Java Domain Application 패키지 계약

상태: CONFIRMED — 2026-08-26
작업 위치: `backend/domain-application/`

## 런타임·빌드 결정

- Java 21
- Spring Boot 4.1.1
- Gradle Kotlin DSL과 Gradle Wrapper
- 기본 패키지: `com.swinganalyzer`
- 동기식 내부 HTTP Client를 사용하고 timeout은 환경 설정으로 주입한다.
- Spring AI, Gemini SDK, FFmpeg를 Java 의존성에 추가하지 않는다.

## 확정된 책임

- Client-facing API
- 사용자·익명 세션·대화·메시지·분석 이력
- 분석 실행 상태와 제품 DB 소유권
- 미디어 메타데이터, 권한, 삭제, 보관 정책
- 사용자 컨텍스트 사실과 근거
- 코칭 주제와 상태 전이
- 로드맵, 마일스톤, 진행 사건과 인정 노출 이력
- Open Loop와 Context Snapshot
- Python/FastAPI 내부 분석 API 호출
- 사용자에게 반환할 최종 응답 조립

## 제안 패키지 구조

기본 패키지: `com.swinganalyzer`

```text
src/main/java/com/swinganalyzer/
├─ SwingAnalyzerApplication.java
├─ analysis/
│  ├─ api/
│  ├─ application/
│  ├─ domain/
│  └─ infrastructure/
│     ├─ persistence/
│     └─ aiclient/
├─ conversation/
│  ├─ api/
│  ├─ application/
│  ├─ domain/
│  └─ infrastructure/
│     ├─ persistence/
│     └─ aiclient/
├─ media/
│  ├─ api/
│  ├─ application/
│  ├─ domain/
│  └─ infrastructure/
│     └─ storage/
└─ shared/
   ├─ config/
   ├─ error/
   └─ persistence/
```

패키지는 기능별로 나누고 각 기능 안에서 `api → application → domain ← infrastructure` 의존 방향을 유지한다.

컨텍스트 코칭 기능은 별도 최상위 도메인을 중복 생성하지 않고 `conversation` 경계 안에 둔다.

- `conversation/domain`: CoachingTopic, Roadmap, Milestone, ProgressEvent, RecognitionExposure, OpenLoop
- `conversation/application`: ContextPacket 조립, 주제 전이, 로드맵 갱신, Progress Moment 판정
- `conversation/infrastructure/aiclient`: Python 내부 API 호출과 CoachingTurnPlan 매핑
- `conversation/infrastructure/persistence`: 컨텍스트와 코칭 상태 저장

## 금지 사항

- Gemini, LangGraph, FFmpeg 분석 로직을 Java에 복제하지 않는다.
- FastAPI의 Domain Policy를 Java에서 다시 구현하지 않는다.
- Java와 Python이 같은 제품 테이블을 동시에 소유하지 않는다.
- Python 내부 모델을 그대로 Client-facing DTO로 노출하지 않는다.
- Java 프로젝트 생성과 기존 Python 코드 이동을 같은 task에서 하지 않는다.

## 확정된 내부 연동

- 내부 API 원본 계약은 `internal-api.openapi.yaml`이다.
- 컨텍스트 코칭의 목표 schema와 상태 규칙은 `context-aware-coaching-contract.md`를 따른다.
- OpenAPI 2.2.0과 공통 fixture는 2026-09-11에 확정했으며 Java 구현 task에서 수정하지 않는다.
- 미디어는 Java가 발급한 짧은 수명의 signed read URL로 전달한다.
- Java와 Python은 서버 전용 Bearer token으로 인증한다.
- Java가 Python을 동기 호출하며 분석 상태와 최종 사용자 응답을 소유한다.
- 모델 비용이 발생한 요청은 timeout 또는 5xx만으로 자동 재시도하지 않는다.
- `analysis_run_id` 중복 실행 차단은 제품 상태를 소유한 Java가 담당한다.

## 공개 API 소유권

Java가 다음 Client-facing API를 소유한다.

- `GET /health`
- `POST /v1/chat`
- `POST /v1/analyze`
- `POST /v1/actions/analyze`
- `GET /v1/actions/openapi.json`
- `GET /v1/history`
- `DELETE /v1/analysis/{run_id}`

Python 내부 응답의 `CoachContent`를 사용자 메시지로 렌더링하는 책임도 Java에 있다.

## 작업 전 출력

Java CLI는 코드 작성 전 다음을 출력하고 사용자 confirm을 기다린다.

```text
읽은 계약문서
담당 책임
수정 예정 패키지
수정 금지 경계
API 변경 여부
DB 변경 여부
실행할 테스트와 curl 경로
미결정사항
```

## 검증 원칙

- 구조 변경과 기능 변경을 분리한다.
- 관련 Java 단위 테스트를 실행한다.
- Client-facing API 또는 FastAPI Client를 변경하면 `curl` integration test를 실행한다.
- 실제 Python 서버 호출 검증 여부와 대체 테스트 여부를 구분해 기록한다.
