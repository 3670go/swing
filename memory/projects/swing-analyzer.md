# 스윙분석기 프로젝트 메모리

## 현재까지 확인된 사실

- 작업 위치는 `C:\Users\user\Desktop\스윙분석기`이다.
- 루트에는 `backend/`, `ui-prototype/`, `AGENTS.md`, `README.md`가 있다.
- `backend/README.md`, `ui-prototype/README.md`, 루트 `README.md`가 새로 작성되었다.
- `AGENTS.md`는 사용자가 프로젝트에 맞게 교체할 예정이다.
- `.env`와 `.youtube_api_key` 같은 실제 시크릿 값은 읽거나 출력하지 않는 운영 원칙을 유지한다.

## Backend

- 위치: `backend/`
- 기술:
  - Python `>=3.11,<3.12`
  - FastAPI
  - LangGraph
  - Google GenAI/Gemini
  - SQLAlchemy/Alembic
  - Supabase
  - Uvicorn
- 주요 endpoint:
  - `GET /health`
  - `POST /v1/chat`
  - `POST /v1/analyze`
  - `POST /v1/actions/analyze`
  - `GET /v1/actions/openapi.json`
  - `GET /v1/history`
  - `DELETE /v1/analysis/{run_id}`
- 확인된 테스트:
  - `python -m unittest discover -s tests -q`: 45개 통과
  - `python -m ruff check .`: 통과
- 확인된 HTTP smoke:
  - `/health`, Action schema, history, auth gate, validation, delete not-found 동작 확인
  - 격리 서버에서 `/v1/chat` E2E 200 확인
  - 기존 8000 서버에서 일시적 502가 있었고, 로그상 Gemini 429 retry가 관찰됨

## UI Prototype

- 위치: `ui-prototype/`
- 기술:
  - React 19
  - Vite
  - TypeScript
  - Playwright
- 목적:
  - 모바일 디바이스 프레임에서 채팅 중심 골프 스윙 분석 UX 검증
  - 사진/영상 첨부 후 분석 draft 검토
  - 백엔드 API 연결 전제 사용자 흐름 확인
- protected runtime 성격:
  - `src/mobile/`
  - device assets
  - runtime scripts
  - `worker/`
- 확인된 npm scripts:
  - `check:runtime`
  - `build`
  - `test:runtime`
  - `test:sites`
  - `dev`

## 프로젝트 개편 전 기준

- 현행 문서는 전체 진입점 역할을 한다.
- 개편의 다음 단계는 기능 추가가 아니라 현재 구조와 목표를 먼저 정렬하는 것이다.
- 백엔드와 UI가 모두 존재하므로 개편 계획은 API 계약, UX 흐름, 데이터/분석 정책, 테스트 체계를 같이 다뤄야 한다.
- 골프 스윙 분석에서는 `FEEL`, `OBSERVATION`, `MEASUREMENT`를 분리해야 한다.
## 결정된 아키텍처 방향

- 백엔드는 Java/Spring Boot Domain Application과 Python/FastAPI AI Processing Unit으로 분리하며, Client는 Spring Boot를 호출하고 Spring Boot가 FastAPI 분석 서버를 내부 호출한다.
- 물리적 Java/Python 서버 분리보다 현재 FastAPI 내부 책임분리를 먼저 진행한다.

## 제타 대화 분석 참고 메모

- 사용자의 명시적 목표와 요구는 모델의 사용자 선호 추정보다 우선한다.
- 코칭 권한은 `사용자: 목표·FEEL·응답 방식`, `AI: 영상 관찰·기술 판정·원인 우선순위`, `공동: 이번 교정과 다음 검증`으로 나눈다.
- 같은 증상에 획일적인 답변을 내지 않도록 `증상 → OBSERVATION → 원인 후보 → 근거 비교 → 우선 원인 → 교정 → 검증 기준` 인과 검사를 최종 답변 전에 수행한다.
- 기술 판정은 증거에 고정하고, 코칭 전략과 표현 방식만 사용자 요구와 대화 맥락에 맞춰 조정한다.

## 아젠다 — 미스샷 용어별 인과 메커니즘

### 뒷땅(Fat Contact)

- `뒷땅`은 원인이 아니라 `공보다 지면을 먼저 친 접촉 결과`다.
- `Low Point`는 클럽 궤도의 결과 상태이므로 단독 원인으로 저장하거나 곧바로 교정에 연결하지 않는다.
- 직접 메커니즘은 `클럽 궤도가 공에 도달하기 전에 지면과 교차함`으로 정의한다.
- 전달 상태는 `궤도 최저점이 뒤로 이동`, `궤도 전체가 과도하게 깊어짐`, `둘 다`, `판정 불가`로 구분한다.
- 원인 후보는 팔·클럽 하강과 골반·몸통 회전의 상대적 타이밍, 팔 신전·손목 풀림, 몸 높이 변화, 압력 이동과 리드사이드 신전, 볼 위치를 근거별로 검사한다.
- `팔·클럽을 너무 빨리 내림`과 `몸이 늦게 돌거나 멈춤`은 동일한 상대적 순서 불일치를 서로 다른 기준에서 표현한 것일 수 있으므로 중복 원인으로 확정하지 않는다.
- 분석 순서는 `미스샷 결과 → 접촉 관찰 → 궤도 메커니즘 → 전달 상태 → 근거가 있는 원인 후보 → 교정 한 가지 → 검증 기준`으로 고정한다.
- 영상만으로 실제 Low Point 수치를 확정하지 않으며, 접촉·잔디·샷 데이터가 없으면 원인 후보와 판정 불가를 구분한다.

