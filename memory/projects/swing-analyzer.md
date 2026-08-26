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

