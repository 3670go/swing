# Memory

## Project
| Name | What |
|------|------|
| 스윙분석기 | 개인 골프 스윙 분석 MVP를 위한 백엔드 API와 모바일 UI 프로토타입 프로젝트 |

## Current State
| Area | Summary |
|------|---------|
| Backend | `backend/` FastAPI API 서버. 채팅, 미디어 분석, 분석 이력, Custom GPT Action 연동을 담당 |
| UI Prototype | `ui-prototype/` React/Vite 모바일 디바이스 프레임 프로토타입 |
| Docs | 루트 `README.md`, `backend/README.md`, `ui-prototype/README.md`가 작성됨 |
| Agent Guide | 사용자는 현재 `AGENTS.md`를 프로젝트에 맞게 교체할 예정 |

## Terms
| Term | Meaning |
|------|---------|
| Backend | FastAPI, LangGraph, Gemini, SQLAlchemy/Alembic, Supabase 기반 API 서버 |
| UI Prototype | React 19, Vite, TypeScript, Playwright 기반 모바일 UX 프로토타입 |
| Custom GPT Action | 백엔드 `/v1/actions/analyze`와 `/v1/actions/openapi.json`으로 연결되는 GPT 파일 분석 연동 |
| FEEL | 사용자가 표현한 골프 스윙 체감. 영상 관찰 사실로 바로 확정하지 않음 |
| OBSERVATION | 영상에서 직접 확인한 움직임 |
| MEASUREMENT | 센서나 런치모니터로 얻은 수치 |

## Preferences
- 한국어로 답변하되 기술 명령과 용어는 원문 병기.
- 확인한 사실과 추정을 분리.
- 시크릿 파일 값은 출력하거나 문서화하지 않음.
- 요청 없이 Git commit, branch 생성, push 금지.
- 프로젝트 개편 전에는 현행 상태를 문서화하고 목표를 먼저 고정.

Full project context: `memory/projects/swing-analyzer.md`
