import { expect, test, type Route } from "@playwright/test";

const account = {
  id: "a709a31e-e7d7-45f7-b48f-322dda6b4607",
  email: "presentation@example.com",
};

function session(sequence: number) {
  const expiresAt = Math.floor(Date.now() / 1000) + 3_600;
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  const accessToken = [
    encode({ alg: "RS256", typ: "JWT" }),
    encode({ sub: account.id, email: account.email, aud: "authenticated", role: "authenticated", exp: expiresAt }),
    `signature-${sequence}`,
  ].join(".");
  const timestamp = new Date().toISOString();

  return {
    access_token: accessToken,
    token_type: "bearer",
    expires_in: 3_600,
    expires_at: expiresAt,
    refresh_token: `refresh-${sequence}`,
    user: {
      id: account.id,
      aud: "authenticated",
      role: "authenticated",
      email: account.email,
      email_confirmed_at: timestamp,
      confirmed_at: timestamp,
      last_sign_in_at: timestamp,
      app_metadata: { provider: "email", providers: ["email"] },
      user_metadata: {},
      identities: [],
      created_at: timestamp,
      updated_at: timestamp,
      is_anonymous: false,
    },
  };
}

async function fulfillJson(route: Route, body: object, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
      "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    },
    body: JSON.stringify(body),
  });
}

test("guest coaching is claimed once and a later login restores without another claim", async ({ page }) => {
  let authSequence = 0;
  let claimCalls = 0;

  await page.route("**/auth/v1/**", async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") {
      await fulfillJson(route, {});
      return;
    }

    const url = new URL(request.url());
    if (url.pathname.endsWith("/signup") || url.pathname.endsWith("/token")) {
      authSequence += 1;
      await fulfillJson(route, session(authSequence));
      return;
    }
    if (url.pathname.endsWith("/logout")) {
      await fulfillJson(route, {});
      return;
    }
    if (url.pathname.endsWith("/user")) {
      await fulfillJson(route, session(authSequence).user);
      return;
    }
    await fulfillJson(route, { message: "Unexpected auth request" }, 404);
  });

  await page.route("http://127.0.0.1:8080/**", async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") {
      await fulfillJson(route, {});
      return;
    }

    const url = new URL(request.url());
    if (request.method() === "POST" && url.pathname === "/v1/chat") {
      await fulfillJson(route, {
        conversation_id: "68d05f53-b1c2-46eb-8382-d377c25e7fbf",
        reply: "출발 방향을 먼저 확인하고 오늘은 전환 속도 한 가지만 점검해 보세요.",
      });
      return;
    }
    if (request.method() === "POST" && url.pathname === "/v1/me/claim") {
      claimCalls += 1;
      await fulfillJson(route, { owner_context_id: "e982cd62-b3cb-4fcc-8630-aae33f2bf987" });
      return;
    }
    if (request.method() === "GET" && url.pathname === "/v1/conversations/latest") {
      await fulfillJson(route, {
        conversation_id: "68d05f53-b1c2-46eb-8382-d377c25e7fbf",
        messages: [
          { message_id: "message-1", role: "user", content: "7번 아이언이 왼쪽으로 가요." },
          { message_id: "message-2", role: "assistant", content: "전환 속도부터 확인해 보세요." },
        ],
      });
      return;
    }
    if (request.method() === "GET" && url.pathname === "/v1/me/profile") {
      await fulfillJson(route, {
        display_name: "발표 검증 골퍼",
        default_handedness: "right",
        current_swing_style: "7번 아이언 왼쪽 당김이 있는 페이드",
        target_swing_style: "일관된 스트레이트 구질",
        body_traits: [{ body_region: null, statement: "다운스윙에서 상체 회전이 빠른 편" }],
        injuries: [],
      });
      return;
    }
    if (request.method() === "GET" && url.pathname === "/v1/me/roadmaps/active") {
      await fulfillJson(route, {
        roadmap: {
          roadmap_id: "roadmap-1",
          target_swing: "7번 아이언 왼쪽 당김을 줄인 스트레이트 구질",
          starting_state: "전환에서 상체가 먼저 열리며 왼쪽 출발이 반복됨",
          current_milestone: {
            title: "전환 속도 낮추기",
            completion_condition: "정면 영상에서 다운스윙 시작 순서가 세 번 연속 유지됨",
            evidence_level: "PLAN_CREATED",
          },
        },
      });
      return;
    }
    await fulfillJson(route, { detail: "Unexpected backend request" }, 404);
  });

  await page.goto("/");
  await page.getByLabel("채팅 메시지 입력").fill("7번 아이언이 왼쪽으로 가요.");
  await page.getByRole("button", { name: "전송" }).click();
  await expect(page.getByText("출발 방향을 먼저 확인하고")).toBeVisible();

  await page.getByRole("button", { name: "메뉴 열기" }).click();
  await page.getByRole("button", { name: "가입 · 로그인" }).click();
  await page.getByLabel("이메일").fill(account.email);
  await page.getByLabel("비밀번호").fill("presentation-password");
  await page.getByRole("button", { name: "가입하고 기록 이어가기" }).click();

  await expect(page.getByText("발표 검증 골퍼 · 코칭 복원됨")).toBeVisible();
  await expect(page.getByRole("status")).toContainText("가입 전 코칭 기록과 회원 상태를 이어받았습니다.");
  expect(claimCalls).toBe(1);

  await page.getByRole("button", { name: "메뉴 열기" }).click();
  await page.getByRole("button", { name: "로그아웃" }).click();
  await expect(page.getByText("채팅 · 가입 전 사용 가능")).toBeVisible();

  await page.getByRole("button", { name: "메뉴 열기" }).click();
  await page.getByRole("button", { name: "가입 · 로그인" }).click();
  await page.getByRole("button", { name: "이미 계정이 있어요 · 로그인" }).click();
  await page.getByLabel("이메일").fill(account.email);
  await page.getByLabel("비밀번호").fill("presentation-password");
  await page.getByRole("button", { name: "로그인하고 로드맵 복원" }).click();

  await expect(page.getByText("발표 검증 골퍼 · 코칭 복원됨")).toBeVisible();
  await expect(page.getByRole("status")).toContainText("회원 세션과 저장된 코칭 상태를 복원했습니다.");
  expect(claimCalls).toBe(1);

  await page.getByRole("button", { name: "메뉴 열기" }).click();
  await page.getByRole("button", { name: "내 스윙 로드맵" }).click();
  await expect(page.getByText("7번 아이언 왼쪽 당김을 줄인 스트레이트 구질")).toBeVisible();
  await expect(page.getByText("전환 속도 낮추기")).toBeVisible();
});
