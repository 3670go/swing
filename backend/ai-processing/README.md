# Swing Analyzer Python Backend — Transition State

현재 공개 API 동작을 유지한 채 `backend/ai-processing`으로 이동한 Python/FastAPI 서버입니다. Java 전환 전까지 미디어 업로드와 분석 실행, 채팅 응답, 분석 이력 조회/삭제, Custom GPT Action 연동을 계속 담당합니다.

목표 구조에서는 내부 AI Processing Unit만 남지만, Java API 전환이 검증되기 전에는 현재 공개 API와 DB 코드를 제거하지 않습니다.

이 문서는 백엔드만 이어받아 실행해야 하는 내부 개발자를 기준으로 작성했습니다. 실제 시크릿 값은 문서화하지 않으며, 환경 변수는 `.env.example`을 기준으로 설정합니다.

## 주요 기능

- `GET /health`: 설정과 외부 연결 구성 상태 확인
- `POST /v1/chat`: 텍스트 기반 골프 스윙 코칭 대화
- `POST /v1/analyze`: 업로드된 사진/영상 기반 분석 실행
- `POST /v1/actions/analyze`: Custom GPT Action에서 전달한 임시 파일 URL 분석
- `GET /v1/actions/openapi.json`: Custom GPT Action용 OpenAPI schema 제공
- `GET /v1/history`: 익명 세션 기준 분석 이력 조회
- `DELETE /v1/analysis/{run_id}`: 분석 결과와 연결 미디어 삭제 표시

## 폴더 구조

- `app/api.py`: FastAPI 앱, HTTP endpoint, 업로드/Action 요청 처리
- `app/config.py`: `.env` 기반 설정 로딩
- `app/database.py`: SQLAlchemy engine/session 구성
- `app/models.py`: 분석 세션, 미디어, 대화, 이력 저장 모델
- `app/schemas.py`: API 요청/응답과 LLM 구조화 출력 schema
- `app/graphs/`: LangGraph 기반 텍스트/미디어 분석 실행 흐름
- `app/repositories/`: DB 저장·조회 계층
- `app/services/`: 업로드 의도 생성 등 도메인 서비스
- `migrations/`: Java DB 전환 전 생성 이력 보존용 Alembic migration
- `tests/`: `unittest` 기반 백엔드 테스트

## 개발 환경

- Python `>=3.11,<3.12`
- 주요 런타임 의존성
  - FastAPI
  - LangGraph
  - Google GenAI
  - SQLAlchemy / Alembic
  - Supabase
  - Uvicorn
- 설치 기준 파일: `requirements.lock`
- 개발용 선택 의존성: `ruff` (`pyproject.toml`의 `dev` extra)

Windows 실행 환경에서는 Application Control 호환을 위해 `orjson`을 `>=3.11.7,<3.12`로 제한합니다. 이 범위를 올릴 때는 단위 테스트에서 DLL 로딩을 먼저 확인합니다.

## 처음 설정

PowerShell 기준입니다.

```powershell
cd backend\ai-processing
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --requirement requirements.lock
Copy-Item ..\.env.example ..\.env
```

그 다음 `backend\.env`를 열어 실제 값을 채웁니다. 물리 분리 전환이 끝날 때까지 현재 설정 위치를 유지합니다. 최소 설정 항목은 다음과 같습니다.

- `DATABASE_URL`: Supabase Postgres transaction pooler 연결 문자열
- `SUPABASE_URL`: Supabase project URL
- `SUPABASE_SECRET_KEY`: 서버 전용 Supabase secret key
- `SUPABASE_STORAGE_BUCKET`: migration으로 생성한 private bucket 이름
- `GEMINI_API_KEY`: 서버 전용 Gemini API key
- `GEMINI_MODEL`: 사용할 Gemini 모델명
- `GPT_ACTION_API_KEY`: Custom GPT Action Bearer 인증용 서버 key
- `GPT_ACTION_FILE_HOSTS`: Custom GPT Action 파일 다운로드 허용 host 목록
- `CORS_ORIGINS`: 로컬 UI prototype origin 목록
- `MAX_VIDEO_BYTES`: 선택 설정. 승인된 업로드 제한이 있을 때만 사용

`.env` 실제 값은 Git, 문서, 로그, 테스트 출력에 남기지 않습니다.

## DB migration

제품 DB migration 소유권은 Java `backend/domain-application`의 Flyway로 이전했습니다.
Python의 Alembic 파일은 전환 기간의 과거 이력 대조용으로만 유지하며 새 migration을 추가하거나
`alembic upgrade`를 실행하지 않습니다. Python 공개 API가 남아 있는 동안에는 런타임 DB 접근만 유지합니다.

## 로컬 실행

```powershell
python -m uvicorn app.api:app --host 0.0.0.0 --port 8000 --reload
```

UI prototype의 기본 API 주소는 `http://127.0.0.1:8000`입니다.

## Java 전용 내부 API

- `GET /internal/health`
- `POST /internal/v1/analyses`
- `POST /internal/v1/coaching/text`

분석·코칭 요청에는 `INTERNAL_API_TOKEN` Bearer 인증이 필요합니다. 분석 미디어는 Supabase private Storage의 signed read URL로만 읽으며 Python은 제품 DB에 저장하지 않습니다. 내부 호출은 Gemini 자동 재시도 없이 한 번만 실행합니다.

요청·응답 기준은 `..\contracts\internal-api.openapi.yaml`과 `..\contracts\fixtures\`입니다.

## 검증

기본 테스트는 현재 저장소의 `unittest` 테스트를 기준으로 실행합니다.

```powershell
python -m unittest discover -s tests -q
```

`ruff`가 설치되어 있으면 lint도 확인합니다.

```powershell
python -m ruff check .
```

README만 수정한 경우 런타임 동작은 바뀌지 않으므로 테스트 실행은 필수는 아닙니다. 코드, migration, 설정 로딩, API surface를 바꾼 경우에는 관련 테스트를 실행한 뒤 인수인계합니다.

## 작업 경계

- 원본 수집 데이터와 시크릿 파일은 덮어쓰거나 출력하지 않습니다.
- `.env.example`은 공유 가능한 placeholder만 유지합니다.
- 공개 함수에는 타입 힌트를 유지합니다.
- 표준 라이브러리로 충분하면 새 의존성을 추가하지 않습니다.
- 요청 없이 Git commit, branch 생성, push를 하지 않습니다.
