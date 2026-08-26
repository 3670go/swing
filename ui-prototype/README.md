# Swing Analyzer UI Prototype

모바일 골프 스윙 분석 UX를 검증하기 위한 React/Vite 프로토타입입니다. 실제 제품 앱 전체가 아니라, 모바일 디바이스 프레임 안에서 채팅과 미디어 기반 분석 흐름을 확인하는 프런트엔드 프로토타입입니다.

현재 방향은 채팅을 기본 화면으로 두고, 사진/영상 첨부 후 분석 draft를 검토한 다음 분석을 시작하는 흐름입니다. 사용자 질문과 `FEEL`은 답변 맥락으로 사용하되, 첨부 미디어는 독립적으로 관찰한 뒤 비교하는 제품 원칙을 UI에 반영합니다.

## 폴더 구조

- `src/Prototype.tsx`: 앱 고유 화면과 상태 흐름의 중심 파일
- `src/prototype.css`: 앱 고유 스타일의 중심 파일
- `src/mobile/`: 모바일 디바이스 프레임, safe area, keyboard, scroll, sheet, carousel runtime
- `src/App.tsx`, `src/main.tsx`, `src/styles.css`: 모바일 runtime을 감싸는 protected entry/runtime 파일
- `public/assets/`: 디바이스 frame, keyboard, status icon, prototype preview 이미지
- `scripts/`: 모바일 runtime hash 검사, lock 갱신, Sites build 준비 스크립트
- `tests/`: Playwright runtime test와 Sites worker test
- `worker/`: Sites/Cloudflare Worker용 server entry
- `.openai/`: Sites hosting metadata

## 개발 환경

- Node.js / npm 기반
- React `19`
- Vite
- TypeScript
- Playwright

의존성 버전은 `package-lock.json`과 `package.json`을 기준으로 맞춥니다.

## 처음 설정

```powershell
cd ui-prototype
npm install
```

백엔드를 함께 붙여 확인해야 하면 `.env.example`을 기준으로 `.env`를 만들고 API 주소를 설정합니다.

```powershell
Copy-Item .env.example .env
```

기본값:

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## 로컬 실행

```powershell
npm run dev -- --port 4173
```

개발 서버 실행 전 `predev`가 자동으로 `npm run check:runtime`을 실행합니다.

## 검증

현재 `package.json`에 정의된 검증 명령입니다.

```powershell
npm run check:runtime
npm run build
npm run test:runtime
npm run test:sites
```

- `npm run check:runtime`: protected mobile runtime 파일이 lock과 일치하는지 확인
- `npm run build`: TypeScript compile, Vite build, Sites용 output 준비
- `npm run test:runtime`: Playwright 기반 모바일 runtime 동작 검증
- `npm run test:sites`: Sites worker output 검증

README만 수정한 경우 런타임 동작은 바뀌지 않으므로 테스트 실행은 필수는 아닙니다. `src/Prototype.tsx`나 `src/prototype.css`를 수정한 경우에도 handoff 전에는 최소 `npm run check:runtime`과 `npm run build`를 확인하는 것이 안전합니다.

## 작업 경계

일반 앱 UI는 주로 다음 파일에서 수정합니다.

- `src/Prototype.tsx`
- `src/prototype.css`

다음은 protected runtime 성격의 파일과 리소스입니다. 사용자가 모바일 runtime 변경을 명시적으로 요청하지 않는 한 수정하지 않습니다.

- `src/App.tsx`
- `src/main.tsx`
- `src/styles.css`
- `src/mobile/`
- `public/assets/iphone/`
- `public/assets/android/`
- `public/assets/status/`
- `vite.config.ts`
- `worker/index.js`
- `scripts/prepare-sites-build.mjs`

runtime 파일을 명시적으로 바꾸는 경우에는 동작을 검증한 뒤 lock hash 갱신 여부를 별도로 판단합니다. 실패를 우회하기 위해 `check:runtime`을 약화하거나 제거하지 않습니다.

## Sites 관련

`npm run build`는 정적 client output과 Sites/Cloudflare Worker output을 함께 준비합니다. 배포 또는 공유가 필요할 때는 build 후 다음 파일들이 있는지 확인합니다.

- `dist/client/index.html`
- `dist/server/index.js`
- `dist/.openai/hosting.json`
- `.openai/hosting.json`

사용자가 명시적으로 공유, 게시, 배포를 요청하지 않으면 Sites 배포는 하지 않습니다.
