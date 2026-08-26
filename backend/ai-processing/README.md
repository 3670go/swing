# Swing Analyzer AI Processing Unit

Java/Spring Boot Domain Application이 내부 호출하는 Python/FastAPI AI 처리 서버입니다.
사용자 앱은 이 서버를 직접 호출하지 않습니다.

## 책임

- 서명된 사진·영상 URL 읽기
- FFmpeg/FFprobe 영상 프레임 추출
- LangGraph 분석 흐름 실행
- Gemini 구조화 출력 호출
- `VisionObservation`, `BaseAssessment`, `CoachContent` 생성

제품 DB 저장, Supabase Storage 업로드·삭제, 사용자 대화문 조립, 공개 API는 Java 서버가 담당합니다.

## 내부 API

- `GET /internal/health`: AI 처리 서버 상태
- `POST /internal/v1/analyses`: 미디어 분석
- `POST /internal/v1/coaching/text`: 텍스트 코칭 내용 생성

두 POST 요청은 `INTERNAL_API_TOKEN` Bearer 인증이 필요합니다. 요청·응답 형식의 기준은
`backend/contracts/ai-processing-api.md`와 `backend/contracts/fixtures`입니다.

## 개발 환경

- Python `>=3.11,<3.12`
- 설치 기준: `requirements.lock`
- 주요 구성: FastAPI, LangGraph, Google GenAI, Pydantic, Uvicorn

PowerShell 기준 처음 한 번 설정합니다.

```powershell
cd C:\Users\user\Desktop\스윙분석기\backend\ai-processing
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --requirement requirements.lock
```

실제 설정은 `backend/.env`에서 읽습니다. Python이 사용하는 값은 다음뿐입니다.

- `SUPABASE_URL`: 서명 URL의 허용 호스트 확인
- `GEMINI_API_KEY`: Gemini 서버 키
- `GEMINI_MODEL`: Gemini 모델명
- `INTERNAL_API_TOKEN`: Java와 공유하는 내부 인증 토큰
- `ANALYSIS_FRAME_COUNT`: 영상당 추출 프레임 수

시크릿은 Git, 문서, 로그, 테스트 출력에 남기지 않습니다.

## 로컬 실행

```powershell
python -m uvicorn app.api:app --host 127.0.0.1 --port 8000
```

Java 서버의 `AI_PROCESSING_BASE_URL` 기본값은 `http://127.0.0.1:8000`입니다.

## 검증

```powershell
python -m ruff check --fix app tests
python -m ruff format app tests
python -m ruff check app tests
python -m unittest discover -s tests -q
```

구조 또는 API 계약을 바꾸면 내부 API를 `curl`로 추가 확인합니다. 유료 Gemini 호출은 비용 승인을
받은 경우에만 실행합니다.
