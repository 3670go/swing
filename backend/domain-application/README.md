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

공통 계약은 `..\contracts\`를 따른다.
