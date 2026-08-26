# 스윙분석기

개인 골프 스윙 분석 MVP를 만들기 위한 프로젝트입니다. 현재 저장소는 크게 두 부분으로 구성됩니다.

- `backend/`: 스윙 분석 API 서버
- `ui-prototype/`: 모바일 UX 프로토타입

백엔드는 사용자의 골프 스윙 관련 질문, 사진/영상 업로드, 분석 결과, 대화 이력을 처리합니다. UI 프로토타입은 모바일 디바이스 프레임 안에서 채팅과 미디어 기반 분석 흐름을 검증합니다.

## 현재 구성 요약

### Backend

`backend/`는 FastAPI 기반 API 서버입니다.

주요 역할:

- 텍스트 기반 골프 스윙 코칭 대화
- 사진/영상 업로드 기반 분석 실행
- 분석 이력 조회와 삭제
- Supabase Storage/DB 연동
- Gemini 기반 구조화 응답 생성
- Custom GPT Action 연동용 endpoint와 OpenAPI schema 제공

상세 실행 방법은 [`backend/README.md`](backend/README.md)를 봅니다.

### UI Prototype

`ui-prototype/`은 React/Vite 기반 모바일 프로토타입입니다.

주요 역할:

- 모바일 디바이스 프레임에서 채팅 UX 확인
- 사진/영상 첨부 후 분석 draft 검토 흐름 확인
- 백엔드 API 연결 전제의 사용자 흐름 검증
- iPhone/Pixel 프레임, safe area, keyboard runtime을 포함한 모바일 상호작용 검증

상세 실행 방법은 [`ui-prototype/README.md`](ui-prototype/README.md)를 봅니다.

## 빠른 실행

### 1. Backend 실행

PowerShell 기준입니다.

```powershell
cd backend\ai-processing
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --requirement requirements.lock
Copy-Item ..\.env.example ..\.env
```

`backend\.env`에 필요한 서버 설정을 채운 뒤 migration과 서버 실행을 진행합니다.

```powershell
python -m alembic upgrade head
python -m uvicorn app.api:app --host 0.0.0.0 --port 8000 --reload
```

기본 API 주소:

```text
http://127.0.0.1:8000
```

### 2. UI Prototype 실행

```powershell
cd ui-prototype
npm install
Copy-Item .env.example .env
npm run dev -- --port 4173
```

기본 UI 개발 서버 주소:

```text
http://127.0.0.1:4173
```

UI의 기본 백엔드 연결값은 다음 형식입니다.

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## 테스트와 검증

### Backend

```powershell
cd backend\ai-processing
python -m unittest discover -s tests -q
python -m ruff check .
```

### UI Prototype

```powershell
cd ui-prototype
npm run check:runtime
npm run build
npm run test:runtime
npm run test:sites
```

`ui-prototype`의 `predev`와 `prebuild`는 protected mobile runtime 검사를 자동으로 실행합니다.

## API 요약

백엔드의 현재 주요 endpoint는 다음과 같습니다.

- `GET /health`: 서버 설정과 provider 구성 상태 확인
- `POST /v1/chat`: 텍스트 기반 코칭 대화
- `POST /v1/analyze`: 업로드 미디어 분석
- `POST /v1/actions/analyze`: Custom GPT Action 파일 분석
- `GET /v1/actions/openapi.json`: Custom GPT Action용 OpenAPI schema
- `GET /v1/history`: 익명 세션 기준 분석 이력 조회
- `DELETE /v1/analysis/{run_id}`: 분석 결과 삭제 처리

## 작업 시 주의사항

- 실제 시크릿 값은 문서, 코드, 로그, 결과 파일에 남기지 않습니다.
- `.env`, `.youtube_api_key` 같은 로컬 시크릿 파일은 필요한 경우에도 값을 출력하지 않습니다.
- 원본 수집 데이터는 덮어쓰거나 삭제하지 않습니다.
- 요청 없이 파일명, 폴더명, 데이터 구조를 변경하지 않습니다.
- 요청 없이 Git commit, branch 생성, push를 하지 않습니다.
- `AGENTS.md`는 프로젝트 운영 지침 파일입니다. 현재 사용자는 이 파일을 프로젝트에 맞게 교체할 예정이며, 이 README 작업에서는 수정하지 않습니다.

## 문서 구조

- [`README.md`](README.md): 프로젝트 전체 요약과 진입점
- [`backend/README.md`](backend/README.md): 백엔드 실행, 설정, 테스트
- [`ui-prototype/README.md`](ui-prototype/README.md): UI 프로토타입 실행, 검증, 작업 경계
