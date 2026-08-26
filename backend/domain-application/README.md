# Swing Analyzer Domain Application

Java/Spring Boot 기반 Client-facing Domain Application이다.

## 책임

- 공개 API
- 사용자와 익명 세션
- 대화, 메시지, 분석 이력과 상태
- 미디어 메타데이터, 권한, 삭제와 보관
- 제품 DB와 migration
- Python AI Processing Unit 내부 호출
- 최종 사용자 응답 조립

Gemini, LangGraph, FFmpeg 분석 로직은 이 프로젝트에 구현하지 않는다.

## 기준

- Java 21
- Spring Boot 4.1.1
- Gradle Kotlin DSL과 Gradle Wrapper
- 기본 패키지 `com.swinganalyzer`

로컬에 Java 21이 없으면 Gradle toolchain이 사용자 Gradle 캐시에 내려받는다. 시스템 JDK 설치를 변경하지 않는다.

## 실행과 검증

PowerShell 기준이다.

```powershell
.\gradlew.bat test --no-daemon
.\gradlew.bat bootRun --no-daemon
```

현재 단계에서는 공개 제품 API를 만들지 않았다. 골격 기동 확인에는 Spring Boot Actuator의 `GET /actuator/health`를 사용한다.

## Python 내부 Client 설정

다음 값이 모두 준비됐을 때만 `AI_PROCESSING_ENABLED=true`로 활성화한다.

- `AI_PROCESSING_BASE_URL`
- `INTERNAL_API_TOKEN`
- `AI_PROCESSING_TIMEOUT_SECONDS`

Client는 `POST /internal/v1/analyses`, `POST /internal/v1/coaching/text`, `GET /internal/health`만 호출한다. 자동 재시도는 하지 않으며 Python의 구조화된 오류를 Java 예외로 변환한다.

Client가 활성화되면 Actuator의 `aiProcessing` health component가 실제 Python health를 확인한다. JDK HttpClient는 Uvicorn과의 호환을 위해 HTTP/1.1로 고정한다.

공통 계약은 `..\contracts\`를 따른다.

## 제품 DB 전환

Java는 기존 Python/Alembic과 같은 Supabase Postgres 스키마를 JPA와 Flyway로 관리한다.
연결에는 `JDBC_DATABASE_URL`, `JDBC_DATABASE_USERNAME`, `JDBC_DATABASE_PASSWORD`를 사용한다.

Flyway는 기본적으로 꺼져 있다. 새 DB에서는 `DB_MIGRATION_ENABLED=true`로 V1부터 적용한다.
기존 Alembic DB에서는 먼저 Alembic revision이 `0003_chat_interaction_metadata`인지 확인한다.
확인된 경우에만 최초 한 번 `DB_MIGRATION_ENABLED=true`, `DB_BASELINE_ON_MIGRATE=true`,
`DB_BASELINE_VERSION=3`으로 기준선을 기록하고, 다음 실행부터 baseline 설정을 다시 끈다.
revision 확인 없이 baseline을 만들거나 기존 DB에 V1을 실행하지 않는다.
