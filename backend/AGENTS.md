# Backend Workspace Contract

이 파일은 `backend/domain-application`과 `backend/ai-processing`에서 작업하는 모든 CLI에 적용한다. 상위 `C:\Users\user\Desktop\스윙분석기\AGENTS.md` 규칙도 함께 따른다.

## 작업 전 필수 문서

코드 작성 전에 다음 계약문서를 모두 읽는다.

1. `contracts/java-package-structure.md`
2. `contracts/python-package-structure.md`
3. `contracts/java-python-boundary.md`
4. `contracts/context-aware-coaching-contract.md`
5. `contracts/internal-api.openapi.yaml`

`contracts/fixtures/`의 요청·응답 예시는 양쪽 구현이 공유하는 contract fixture다.

`internal-api.openapi.yaml` 2.0.0과 `contracts/fixtures/`는 2026-08-26 동결 계약이다.
Java/Python 구현 task에서는 수정하지 않고, 변경이 필요하면 별도 계약 변경 plan과 confirm을
먼저 받는다.

문서의 `확정`과 `미결정`을 구분한다. 미결정 항목을 확정 계약처럼 구현하지 않는다.

## 작업 공간 경계

- Java/Spring Boot 작업 기본 경로: `domain-application/`
- Python/FastAPI 목표 작업 경로: `ai-processing/`
- 현재 Python 실행 기준은 `backend/ai-processing/app`, `backend/ai-processing/tests`다.
- 공통 계약 변경은 Java 또는 Python 구현과 분리한다.
- 다른 작업 공간의 코드는 명시적 승인 없이 수정하지 않는다.

## 작업 전 출력 및 승인

작업자는 코드 작성 전에 다음을 출력한다.

```text
읽은 계약문서
담당 작업 공간
구조 변경 또는 기능 변경
수정 예정 경로
수정 금지 경로
API 및 데이터 계약 영향
실패 경로
되돌리기 기준
실행할 테스트와 curl 검증
미결정사항
```

사용자가 confirm하고 범위를 이해하기 전에는 코드, 스키마, API를 변경하지 않는다.

## 검증

- 구조 변경과 기능 변경을 별도로 검증한다.
- 변경한 작업 공간의 단위 테스트와 formatter/linter를 실행한다.
- API 변경 후 관련 경로를 `curl`로 integration test한다.
- 실행하지 않은 Provider E2E와 검증 공백을 숨기지 않는다.
