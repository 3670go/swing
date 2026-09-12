# Python AI Processing Unit 패키지 계약

상태: CONFIRMED — 2026-08-26
목표 작업 위치: `backend/ai-processing/`

## 전환 상태

현재 FastAPI 코드는 `backend/ai-processing/app`, `backend/ai-processing/tests`에 있다.
Java 전용 내부 API 전환과 Python 공개 API·제품 DB 접근 제거가 완료됐으며,
Python은 AI Processing Unit 책임만 가진다.

## 확정된 책임

- Spring Boot 전용 내부 분석 API
- Spring Boot 전용 내부 텍스트 코칭 API
- 사진·영상 분석 처리
- FFmpeg/FFprobe 프레임 추출
- Gemini API 및 LangGraph 실행
- FEEL/OBSERVATION/MEASUREMENT 분석 규약
- VisionObservation, BaseAssessment, CoachContent 생성
- ContextPacket 해석
- CoachingTurnPlan 후보 생성
- 영상 관찰과 기존 컨텍스트의 일치·충돌 판정
- 주제 재정의, 로드맵 갱신, 진행 인정, Open Loop 후보 생성
- 구조화된 분석 결과를 Spring Boot에 반환

## 목표 패키지 구조

```text
ai-processing/
├─ pyproject.toml
├─ app/
│  ├─ api/
│  │  └─ internal/
│  │     ├─ analysis.py
│  │     ├─ coaching.py
│  │     └─ health.py
│  ├─ application/
│  │  ├─ analyze_swing.py
│  │  └─ failures.py
│  ├─ domain/
│  │  ├─ models.py
│  │  ├─ analysis_policy.py
│  │  └─ evidence_policy.py
│  ├─ ports/
│  │  ├─ frame_extractor.py
│  │  ├─ swing_analyzer.py
│  │  └─ media_reader.py
│  ├─ adapters/
│  │  ├─ ffmpeg_frame_extractor.py
│  │  ├─ langgraph_swing_analyzer.py
│  │  ├─ gemini_model.py
│  │  └─ signed_url_media_reader.py
│  └─ graphs/
│     ├─ runtime.py
│     ├─ coaching_state.py
│     ├─ coaching_nodes.py
│     └─ coaching_guards.py
└─ tests/
```

추가된 graph 파일은 목표 책임 배치다. 기존 graph 구현을 한 번에 이동하지 않고,
기능 변경과 분리한 구조 변경 task에서 순차적으로 맞춘다.

## 전환 후 제거할 책임

- Client-facing 대화 API
- 사용자·대화·메시지·분석 이력 제품 DB
- 제품 분석 상태와 삭제·보관 정책
- 사용자에게 반환하는 최종 API 응답 조립

Python에는 제품 Repository와 migration을 두지 않는다.
컨텍스트와 코칭 상태는 Java가 저장하고, Python은 요청에 포함된 ContextPacket만 사용한다.

## 확정된 내부 API

- `GET /internal/health`
- `POST /internal/v1/analyses`
- `POST /internal/v1/coaching/text`
- 요청·응답 원본 계약은 `internal-api.openapi.yaml`이다.
- 컨텍스트 코칭의 목표 schema와 상태 규칙은 `context-aware-coaching-contract.md`를 따른다.
- OpenAPI 2.2.0과 공통 fixture는 2026-09-11에 확정했으며 Python 구현 task에서 수정하지 않는다.
- 분석·코칭 요청은 응답이 완성될 때까지 기다리는 동기 HTTP 방식이다.
- 분석 미디어는 signed read URL에서 임시 디렉터리로 내려받고 요청 종료 후 제거한다.
- Python은 signed URL, 사용자 원문, 인증 token을 로그에 남기지 않는다.
- Python은 제품 DB와 Supabase Storage를 직접 수정하지 않는다.

## 금지 사항

- 사용자 질문이나 FEEL을 영상 OBSERVATION 생성에 사용하지 않는다.
- FastAPI가 Java 소유 제품 DB를 직접 수정하지 않는다.
- Spring Boot 전용 내부 DTO와 Domain Model을 혼합하지 않는다.
- 폴더 이동 중 API 계약이나 분석 결과를 변경하지 않는다.
- 실제 시크릿을 문서, 테스트 출력, Git에 남기지 않는다.
- Java가 소유한 공개 `/v1/*` 경로를 Python에 새로 만들지 않는다.
- 모델 비용이 발생한 호출을 Python에서 투명하게 자동 재시도하지 않는다.

## 작업 전 출력

Python CLI는 코드 작성 전 다음을 출력하고 사용자 confirm을 기다린다.

```text
읽은 계약문서
현재 실행 경로와 목표 경로
담당 책임
수정 예정 파일
수정 금지 경계
API 변경 여부
분석 규약 영향 여부
실행할 ruff, unittest, curl
미결정사항
```

## 검증 원칙

```text
python -m ruff check --fix app tests
python -m ruff format app tests
python -m ruff check .
python -m unittest discover -s tests -q
```

구조 또는 API 변경 후 관련 FastAPI 경로를 `curl`로 검증한다. Provider E2E를 실행하지 않으면 해당 검증 공백을 명시한다.
