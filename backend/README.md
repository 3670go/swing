# Swing Analyzer Backend Workspace

백엔드는 다음 두 작업 공간으로 분리한다.

- `domain-application/`: Java/Spring Boot Client-facing Domain Application
- `ai-processing/`: Python/FastAPI AI Processing Unit

현재 Python 실행 코드는 `ai-processing/`으로 이동했다. Java 구현과 내부 API 전환이 끝나기 전까지 Python의 기존 공개 API와 제품 DB 코드는 전환 책임으로 유지한다.

작업 전 다음 파일을 먼저 읽는다.

1. `AGENTS.md`
2. `contracts/java-package-structure.md`
3. `contracts/python-package-structure.md`
4. `contracts/java-python-boundary.md`
5. `contracts/internal-api.openapi.yaml`

서비스별 실행 방법은 각 작업 공간의 README를 따른다.
