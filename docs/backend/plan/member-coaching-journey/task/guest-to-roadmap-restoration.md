# 작업계획 — 가입 전 채팅부터 재로그인 로드맵 복원

> 상태: 구현 승인 — 2026-09-11

## 1. 목표

비회원이 채팅과 미디어 분석으로 서비스를 먼저 체험한 뒤 이메일 회원으로 전환하고, 기존
대화·분석을 계정에 인계한다. 회원 프로필과 개인 스윙 로드맵은 로그아웃 후 재로그인해도 같은
회원 소유 상태로 복원한다.

```text
비회원 채팅·분석
→ 이메일 회원가입 또는 로그인
→ 익명 owner_context 인계
→ 장기 프로필 저장
→ 최근 분석에서 개인 로드맵 생성
→ 로그아웃
→ 재로그인
→ 대화·프로필·로드맵 복원
```

## 2. 책임 경계

### Java/Spring Boot

- Supabase access token 검증
- 익명·회원 요청의 OwnerContext 결정
- 익명 OwnerContext의 회원 계정 인계
- 회원 프로필, 대화, 분석, 로드맵 소유권 검증
- 프로필과 로드맵 공개 API
- 로드맵 생성·진행 상태의 결정적 검증

### Python/FastAPI

- 인증과 회원 DB를 소유하지 않는다.
- Java가 선택한 ContextPacket만 사용한다.
- Blind Analysis 입력에는 회원 프로필과 과거 코칭 상태를 넣지 않는다.
- 동결된 Observation과 BaseAssessment 이후에만 맥락을 사용한다.

### UI Prototype

- Supabase 이메일 회원가입·로그인·로그아웃·세션 복원
- access token을 Java 공개 API의 Bearer header로 전달
- 익명 session id를 계정 인계 시점까지 보존
- 프로필 편집과 활성 로드맵 표시

## 3. 단계별 task

### backend → member-identity → supabase-auth-owner-binding

1. Spring Security Resource Server 의존성과 JWT 검증 설정을 추가한다.
2. 공개 API에서 bearer token을 선택적으로 읽는 OwnerIdentityResolver를 만든다.
3. 익명 요청은 기존 anonymous session hash로 처리한다.
4. 인증 요청은 `external_provider=supabase`, `external_subject=JWT sub`로 처리한다.
5. 계정 인계 API는 기존 익명 owner에 external subject를 연결한다.
6. 같은 요청을 반복해도 같은 owner를 반환한다.
7. 다른 owner가 이미 같은 external subject를 소유하면 409로 거부하고 자동 병합하지 않는다.

### backend → member-profile → persistent-profile

1. `owner_contexts`의 표시 이름과 기본 손잡이를 회원 프로필로 사용한다.
2. 장기 골프 정보는 `user_context_facts`의 확정 유형을 사용한다.
3. 프로필 조회·수정 API를 추가한다.
4. 인증된 회원만 프로필 API를 호출할 수 있다.
5. 관련 프로필 사실만 ContextPacket에 포함한다.
6. 부상 정보는 계약대로 마지막 명시 시점부터 90일 후 만료한다.

### backend → personal-roadmap → create-read-progress

1. 회원의 활성 코칭 주제와 성공한 최근 분석에서 로드맵을 생성한다.
2. topic당 활성 로드맵은 하나만 허용한다.
3. 최초 milestone은 분석의 한 가지 교정과 검증 기준으로 만든다.
4. 활성 로드맵 조회 API를 제공한다.
5. 사용자 보고는 `USER_REPORTED_PROGRESS`, 현재 영상 Observation은
   `VIDEO_VERIFIED_PROGRESS`까지만 올릴 수 있다.
6. 한 요청에서 milestone 상태는 최대 한 번만 상승하며 하향하지 않는다.

### ui-prototype → member-coaching → auth-profile-roadmap-surfaces

1. 회원가입·로그인 surface를 추가한다.
2. 로그인 세션을 복원하고 모든 Java 요청에 access token을 보낸다.
3. 익명 상태에서 로그인하면 owner claim API를 한 번 호출한다.
4. 회원 프로필 조회·편집 surface를 추가한다.
5. 분석 결과에서 `내 로드맵으로 저장` 동작을 제공한다.
6. 채팅 메뉴에서 활성 로드맵을 복원해 표시한다.

## 4. 공개 API 변경

기존 chat/analyze/history/delete request와 response body는 유지한다. 인증된 요청은 선택적인
`Authorization: Bearer <Supabase access token>`을 추가한다.

신규 API:

- `POST /v1/me/claim`
- `GET /v1/conversations/latest`
- `GET /v1/me/profile`
- `PUT /v1/me/profile`
- `POST /v1/me/roadmaps`
- `GET /v1/me/roadmaps/active`

## 5. 데이터 규칙

- 제품 데이터의 소유 기준은 항상 `owner_contexts.id`다.
- JWT subject를 conversation, analysis, roadmap 테이블에 직접 복제하지 않는다.
- 계정 인계는 기존 owner row의 외부 identity만 설정해 하위 FK를 보존한다.
- 비밀번호와 refresh token은 제품 DB에 저장하지 않는다.
- 다른 회원의 conversation, analysis 또는 roadmap id는 404로 처리한다.

## 6. 실패 경로

| 상황 | 결과 |
|---|---|
| bearer token 없음 | 기존 익명 흐름 유지 |
| 잘못됐거나 만료된 token | 401 |
| 회원 전용 API의 token 없음 | 401 |
| 같은 외부 subject가 다른 owner에 연결됨 | 409, 자동 병합 없음 |
| 다른 회원 데이터 접근 | 404 |
| roadmap 생성 조건 부족 | 422 |
| 분석 실패 | roadmap과 milestone 변경 없음 |

## 7. 되돌리기

- Python 내부 OpenAPI 2.2.0과 fixture는 변경하지 않는다.
- 기존 공개 API body를 유지해 인증 기능 제거 시 익명 흐름으로 돌아갈 수 있게 한다.
- migration과 기능 구현을 분리한다.
- 실DB에는 migration을 자동 적용하지 않는다.

## 8. 완료 판정

1. 익명 사용자의 채팅과 분석 결과가 저장된다.
2. 회원가입 후 같은 owner id에 외부 subject가 연결된다.
3. 프로필을 저장하고 코칭 ContextPacket에서 다시 읽는다.
4. 성공한 분석으로 활성 로드맵과 최초 milestone을 만든다.
5. 로그아웃 후 같은 회원으로 로그인한다.
6. 이전 대화·분석·프로필·활성 로드맵이 복원된다.
7. 다른 회원은 해당 데이터에 접근할 수 없다.
8. Java/Python 단위 테스트, UI build와 관련 curl integration이 통과한다.

## 9. 제외 범위

- 소셜 로그인, MFA, 비밀번호 재설정, 관리자 권한
- 회원 간 데이터 자동 병합
- 결제와 구독
- Vector DB
- 실시간 카메라 분석
- 복수 영상 자동 비교의 추가 개발
- 여러 활성 로드맵
- 로드맵 수동 순서 변경과 과거 version 복구 UI
