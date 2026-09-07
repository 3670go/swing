# AGENTS.md

## 프로젝트 작업 기준

모든 프로젝트 작업은 `C:\Users\user\Desktop\스윙분석기`를 기준으로 한다.

현재 프로젝트는 큰 task를 잘게 쪼개기보다, 문서 안에서 다음 계층으로 관리한다.

```text
{projectname}
  → plan
    → task
```

예:

```text
backend
  → api-architecture-refactor
    → chat-usecase-separation
    → analysis-usecase-separation
    → repository-port-separation

ui-prototype
  → media-chat-flow
    → upload-draft-ui
    → analysis-result-rendering
```

## 현재 폴더 구조

```text
C:\Users\user\Desktop\스윙분석기
  ├─ backend/
  │  └─ 개인 골프 스윙 분석 API 서버
  ├─ ui-prototype/
  │  └─ 모바일 채팅형 스윙 분석 UI 프로토타입
  ├─ memory/
  │  └─ 프로젝트 작업 기억과 정리 자료
  ├─ README.md
  │  └─ 프로젝트 전체 설명 문서
  ├─ swing-analyze.md
  │  └─ 현재 아키텍처 재분석과 개편 목표 문서
  ├─ CLAUDE.md
  │  └─ 보조 에이전트/도구용 작업 기준 문서
  └─ AGENTS.md
     └─ Codex 작업 기준 문서
```

## Task 문서 관리 규칙

- task는 항상 문서 내에서 `{projectname} -> plan -> task` 순서로 정리한다.
- `{projectname}`은 실제 프로젝트 또는 하위 시스템 이름을 사용한다. 예: `backend`, `ui-prototype`, `memory`, `docs`.
- `plan`은 대카테고리다. 기능명이나 구조 변경 목표처럼 여러 task를 묶을 수 있는 이름을 사용한다.
- `task`는 실제 실행 단위다. 너무 작게 쪼개지 말고, 사용자가 이해하고 확인할 수 있는 단위로 둔다.
- task를 실행하기 전에 먼저 plan을 제시한다.
- 사용자가 confirm하고 변경 범위를 이해하기 전에는 작업하지 않는다.

## 변경 분리 원칙

- 구조적 변경과 기능적 변경은 별도로 진행한다.
- 같은 작업에서 구조 변경과 기능 변경을 섞지 않는다.
- 구조적 변경은 API 동작을 바꾸지 않는 책임 분리, 파일 이동, 레이어 분리, 의존성 방향 정리다.
- 기능적 변경은 사용자 동작, API 계약, 응답 내용, 저장 데이터, UI 기능, 분석 결과가 바뀌는 변경이다.

## 검증 원칙

- 구조적 변경 또는 기능적 변경 후에는 관련 API를 `curl`로 호출하는 integration test를 원칙으로 한다.
- `curl` integration test를 실행하지 못하면 완료로 보고하지 않고, 실행하지 못한 이유와 검증 공백을 명시한다.

## 백엔드 책임분리 결정

- 백엔드는 Java/Spring Boot Domain Application과 Python/FastAPI AI Processing Unit으로 분리한다.
- Client는 Spring Boot를 호출하고, Spring Boot가 FastAPI 분석 서버를 내부 호출한다.
- 먼저 현재 FastAPI 내부 책임분리를 진행하고, Java/Python 물리 서버 분리는 그 다음 단계로 진행한다.
- Python/FastAPI에는 AI 분석 책임만 남긴다.
- Java/Spring Boot는 Client-facing Domain Application과 제품 DB 소유권을 가진다.

