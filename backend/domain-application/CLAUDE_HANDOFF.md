# Claude Handoff — Java Domain Application Task 1

작성 시점: 2026-08-28  
작업 위치: `C:\Users\user\Desktop\스윙분석기\backend\domain-application`

## 작업 범위

이 터미널의 담당 범위는 Java/Spring Boot `domain-application`이다.

수정 금지 경계:

- `backend/ai-processing/`
- `backend/contracts/internal-api.openapi.yaml`
- `backend/contracts/fixtures/`
- 기타 계약 문서
- 실제 Gemini 자동 호출
- Git commit, branch, push

## 완료된 작업

완료된 작업은 Java Task 1, 즉 Context-Aware Chat Engine용 DB migration 보완과 검증이다.

변경 파일:

```text
src/main/resources/db/migration/V5__context_aware_coaching_state.sql
src/test/java/com/swinganalyzer/shared/persistence/ContextAwareCoachingMigrationTests.java
```

### V5 migration 내용

신규 테이블:

- `coaching_topics`
- `roadmaps`
- `roadmap_milestones`
- `user_context_facts`
- `progress_events`
- `recognition_events`
- `open_loops`
- `context_snapshots`
- `coaching_request_applications`

중요 제약:

- 사용자당 `ACTIVE` CoachingTopic 최대 1개
  - `ux_coaching_topics_one_active_per_owner`
- topic당 `PENDING` OpenLoop 최대 1개
  - `ux_open_loops_one_pending_per_topic`
- ProgressEvent당 RecognitionEvent 최대 1개
  - `ux_recognition_events_progress_event_id`
- `ContextSnapshot.request_id` 중복 방지
  - `ux_context_snapshots_request_id`
- `coaching_request_applications.request_id` 중복 적용 방지
  - primary key
- `coaching_request_applications.applied`와 `blocked_reason` 양방향 정합성
  - `applied = true`이면 `blocked_reason IS NULL`
  - `applied = false`이면 `blocked_reason IS NOT NULL`이고 허용 enum 중 하나
- `roadmaps.current_milestone_id`는 같은 roadmap 소속 milestone만 참조
  - `(roadmaps.id, roadmaps.current_milestone_id)`
  - `roadmap_milestones(roadmap_id, id)` 복합 FK

주의: PostgreSQL `CHECK`는 결과가 `NULL`이면 통과하므로, `blocked_reason IS NOT NULL`을 명시적으로 넣었다.

## 검증 결과

실제 disposable PostgreSQL 컨테이너에서 V1~V5 Flyway migration test를 실행했다.

실행한 테스트:

```powershell
.\gradlew.bat test --tests com.swinganalyzer.shared.persistence.ContextAwareCoachingMigrationTests --no-daemon
```

확인한 결과:

```text
tests=7
skipped=0
failures=0
errors=0
```

검증된 항목:

- V1~V5 migration 실제 PostgreSQL 적용
- migration 재실행 시 중복 적용 없음
- `applied=true + blocked_reason 존재` 거부
- `applied=false + blocked_reason=null` 거부
- 다른 Roadmap milestone 연결 거부
- ACTIVE topic 중복 거부
- PENDING OpenLoop 중복 거부
- ProgressEvent당 RecognitionEvent 중복 거부

임시 PostgreSQL 컨테이너는 테스트 후 제거했다. `.migration-test-*` 임시 파일도 제거했다.

## 현재 확인된 Git 상태

Java domain-application 기준 변경 파일은 다음 두 개다.

```text
?? backend/domain-application/src/main/resources/db/migration/V5__context_aware_coaching_state.sql
?? backend/domain-application/src/test/java/com/swinganalyzer/shared/persistence/ContextAwareCoachingMigrationTests.java
```

현재 작업자는 Python, OpenAPI, fixture, 계약 문서를 수정하지 않았다.

## 아직 하지 않은 것

- Task 2 구현
- Java DTO를 OpenAPI 2.0.0으로 교체
- ContextPacket 조립
- CoachingTurnPlan 검증, 저장, 응답 조립
- Java 공개 API에서 Python 내부 API까지 curl 통합 검증
- 실제 Gemini Provider E2E
- commit, branch, push

## 다음 Java Task 2 후보

다음 confirm 후 진행할 후보는 `OpenAPI 2.0.0 Java DTO 구현`이다.

주요 파일:

```text
src/main/java/com/swinganalyzer/analysis/application/model/AiProcessingContract.java
src/main/java/com/swinganalyzer/analysis/infrastructure/aiclient/RestAiProcessingClient.java
src/test/java/com/swinganalyzer/analysis/infrastructure/aiclient/RestAiProcessingClientTests.java
```

필요 작업:

- `AnalysisRequest`를 `media + ContextPacket` 구조로 변경
- `TextCoachingRequest`를 `requestId + ContextPacket` 구조로 변경
- `AnalysisResponse`와 `TextCoachingResponse`에 `CoachingTurnPlan` 반영
- 다음 DTO 구현
  - `ContextPacket`
  - `RequestContext`
  - `ActiveCoachingTopic`
  - `CoachingScope`
  - `RoadmapContext`
  - `RoadmapMilestoneSummary`
  - `AnalysisEpisodeSummary`
  - `UserContextFact`
  - `PendingOpenLoop`
  - `RecognitionContext`
  - `CoachingTurnPlan`
  - 모든 candidate DTO
  - `EvidenceReference`
- fixture 4개 역직렬화 테스트
- 전송 JSON이 동결 fixture와 일치하는지 테스트
- unknown field와 잘못된 enum 거부 테스트

Task 2는 기능 변경이다. Task 1 DB migration 변경과 섞지 않는다.

## Python과 충돌 가능성

현재 Task 1 변경은 Java/Flyway migration과 Java migration test뿐이라 Python 파일과 직접 충돌하지 않는다.

다만 Task 2부터 Java DTO가 동결 OpenAPI 2.0.0에 맞게 바뀐다. Python 구현이 같은 OpenAPI/fixture와 완전히 일치하지 않으면 Java-Python 통합 테스트에서 계약 불일치가 드러날 수 있다. 그 경우에도 Java 쪽에서 Python 코드를 수정하지 말고, Python 담당 작업으로 분리해야 한다.
