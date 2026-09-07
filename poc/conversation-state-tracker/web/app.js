"use strict";
/* 대화 상태 추적 POC 클라이언트.
   서버에 아무것도 저장하지 않는다. 대화는 localStorage 에만 남는다. */

const STORE_KEY = "conversation-state-tracker-poc/v1";

const FEEDBACK_BUTTONS = [
  ["HELPFUL", "도움 됐어요"],
  ["HARD_TO_UNDERSTAND", "이해하기 어려워요"],
  ["NOT_MY_PROBLEM", "내 문제와 달라요"],
  ["ACTUALLY_IMPROVED", "실제로 해보니 좋아졌어요"],
  ["TOO_LONG", "답변이 너무 길어요"],
];

const DEFAULT_TOPICS = [
  { topic_id: "t1", user_problem: "드라이버를 당겨 친다", root_problem: "전환에서 팔이 내려올 공간이 부족하다" },
  { topic_id: "t2", user_problem: "아이언에서 뒤땅이 난다", root_problem: "체중이 오른발에 남는다" },
];

let store = null;
let lastState = null;

/* ---------------- storage ---------------- */

function freshStore() {
  return {
    user_id: "poc-user",
    conversation_id: "poc-conversation",
    topics: JSON.parse(JSON.stringify(DEFAULT_TOPICS)),
    activeTopicId: "t1",
    messages: [],
    behavior_events: [],
    feedback_events: [],
    video_evidence: [],
    open_loops: [],
    prior_state: null,
    seq: 0,
  };
}

function load() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) return JSON.parse(raw);
  } catch (err) {
    /* 저장소를 못 읽어도 화면은 떠야 한다 */
  }
  return freshStore();
}

function save() {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(store));
  } catch (err) {
    /* 저장 실패는 무시한다. 서버에는 어차피 남기지 않는다 */
  }
}

function nextId(prefix) {
  store.seq += 1;
  return `${prefix}${store.seq}`;
}

function nowIso() {
  return new Date().toISOString();
}

/* ---------------- payload ---------------- */

function activeTopic() {
  return store.topics.find((t) => t.topic_id === store.activeTopicId) || null;
}

function buildPayload() {
  return {
    user_id: store.user_id,
    conversation_id: store.conversation_id,
    messages: store.messages,
    behavior_events: store.behavior_events,
    feedback_events: store.feedback_events,
    video_evidence: store.video_evidence,
    active_coaching_topic: activeTopic(),
    open_loops: store.open_loops,
    prior_state: store.prior_state,
  };
}

async function callTrack() {
  const response = await fetch("/api/track", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildPayload()),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const message = data && data.error ? `${data.error.code}: ${data.error.message}` : `HTTP ${response.status}`;
    throw new Error(message);
  }
  return data;
}

async function refresh(appendReply) {
  const errorBox = document.getElementById("panel-error");
  try {
    const data = await callTrack();
    errorBox.hidden = true;
    lastState = data.conversation_state;
    if (appendReply) {
      store.messages.push({
        message_id: nextId("m"),
        role: "assistant",
        text: data.demo_reply,
        created_at: nowIso(),
        topic_id: store.activeTopicId,
      });
    }
    store.prior_state = data.conversation_state;
    save();
    renderMessages();
    renderPanel(lastState);
  } catch (err) {
    errorBox.hidden = false;
    errorBox.textContent = `요청 실패 — ${err.message}`;
  }
}

/* ---------------- chat rendering ---------------- */

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function topicLabel(topicId) {
  const topic = store.topics.find((t) => t.topic_id === topicId);
  return topic ? `${topic.topic_id} · ${topic.user_problem}` : topicId || "(주제 없음)";
}

function renderMessages() {
  const box = document.getElementById("messages");
  box.innerHTML = "";
  if (store.messages.length === 0) {
    box.appendChild(el("p", "empty", "메시지를 입력해 시작하세요."));
    return;
  }
  for (const message of store.messages) {
    const wrap = el("div", `msg ${message.role}`);
    wrap.appendChild(el("div", "meta", `${message.role} · ${message.message_id} · ${topicLabel(message.topic_id)}`));
    wrap.appendChild(el("div", "body", message.text));
    if (message.role === "assistant") wrap.appendChild(feedbackRow(message));
    box.appendChild(wrap);
  }
  box.scrollTop = box.scrollHeight;
}

function feedbackRow(message) {
  const row = el("div", "feedback");
  const chosen = store.feedback_events.filter((f) => f.target_message_id === message.message_id);
  const chosenTypes = new Set(chosen.map((f) => f.feedback_type));
  const reasonInput = el("input");
  reasonInput.type = "text";
  reasonInput.placeholder = "이유 (선택)";

  for (const [type, label] of FEEDBACK_BUTTONS) {
    const button = el("button", chosenTypes.has(type) ? "chosen" : null, label);
    button.type = "button";
    button.addEventListener("click", async () => {
      if (chosenTypes.has(type)) return;
      store.feedback_events.push({
        feedback_id: nextId("f"),
        target_message_id: message.message_id,
        feedback_type: type,
        reason: reasonInput.value.trim() || null,
        created_at: nowIso(),
        topic_id: message.topic_id,
      });
      save();
      await refresh(false);
    });
    row.appendChild(button);
  }
  row.appendChild(reasonInput);
  return row;
}

/* ---------------- state panel ---------------- */

function confidenceTag(value) {
  const cls = value === "HIGH" ? "tag hi" : value === "LOW" ? "tag lo" : "tag";
  return el("span", cls, value);
}

function kv(pairs) {
  const list = el("dl", "kv");
  for (const [key, value] of pairs) {
    list.appendChild(el("dt", null, key));
    const dd = el("dd");
    if (value instanceof Node) dd.appendChild(value);
    else dd.textContent = value;
    list.appendChild(dd);
  }
  return list;
}

function evidenceTags(refs) {
  const wrap = el("div");
  if (!refs || refs.length === 0) {
    wrap.appendChild(el("span", "empty", "없음"));
    return wrap;
  }
  for (const ref of refs) wrap.appendChild(el("span", "tag", `${ref.source_type}:${ref.source_id}`));
  return wrap;
}

function setPanel(id, node) {
  const host = document.getElementById(id);
  host.innerHTML = "";
  host.appendChild(node);
}

function renderPanel(state) {
  if (!state) return;

  const topic = state.active_coaching_topic;
  setPanel(
    "p-topic",
    topic
      ? kv([
          ["topic_id", topic.topic_id],
          ["사용자 문제", topic.user_problem],
          ["근본 문제", topic.root_problem || "(없음)"],
        ])
      : el("p", "empty", "활성 주제 없음"),
  );

  setPanel("p-intent", el("p", null, state.explicit_intent));

  const needsBox = el("div");
  if (state.inferred_needs.length === 0) needsBox.appendChild(el("p", "empty", "추정한 니즈 없음"));
  for (const need of state.inferred_needs) {
    const item = el("div", "item");
    const head = el("div");
    head.appendChild(el("strong", null, need.need_type));
    head.appendChild(document.createTextNode(" "));
    head.appendChild(confidenceTag(need.confidence));
    item.appendChild(head);
    item.appendChild(el("div", "why", need.reason));
    item.appendChild(evidenceTags(need.evidence));
    needsBox.appendChild(item);
  }
  setPanel("p-needs", needsBox);

  const engagement = state.engagement_state;
  const engagementBox = el("div");
  engagementBox.appendChild(
    kv([
      ["level", engagement.level],
      ["trend", engagement.trend],
      ["confidence", confidenceTag(engagement.confidence)],
    ]),
  );
  engagementBox.appendChild(el("div", "why", engagement.reason));
  engagementBox.appendChild(evidenceTags(engagement.evidence));
  setPanel("p-engagement", engagementBox);

  const progress = state.progress;
  const progressBox = el("div");
  progressBox.appendChild(
    kv([
      ["근거 수준", progress.level],
      ["영상으로 확인됨", progress.swing_improvement_confirmed ? "예" : "아니오 (사용자 보고 단계)"],
      ["인정 강도 상한", progress.recognition_intensity_cap],
      ["confidence", confidenceTag(progress.confidence)],
    ]),
  );
  progressBox.appendChild(el("div", "why", progress.reason));
  progressBox.appendChild(evidenceTags(progress.evidence));
  setPanel("p-progress", progressBox);

  setPanel(
    "p-strategy",
    kv([
      ["주 전략", state.next_response_strategy],
      ["보조 전략", state.secondary_strategy || "(없음)"],
    ]),
  );

  const allRefs = [];
  allRefs.push(...engagement.evidence, ...progress.evidence);
  for (const need of state.inferred_needs) allRefs.push(...need.evidence);
  for (const fact of state.confirmed_user_facts) allRefs.push(fact.source);
  const seen = new Set();
  const unique = allRefs.filter((ref) => {
    const key = `${ref.source_type}:${ref.source_id}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  setPanel("p-evidence", evidenceTags(unique));

  const contextBox = el("div");
  if (state.selected_context_message_ids.length === 0) {
    contextBox.appendChild(el("span", "empty", "없음"));
  } else {
    for (const id of state.selected_context_message_ids) {
      const message = store.messages.find((m) => m.message_id === id);
      contextBox.appendChild(el("span", "tag", message ? `${id} (${message.topic_id || "-"})` : id));
    }
  }
  setPanel("p-context", contextBox);

  const loopBox = el("div");
  if (state.unresolved_open_loops.length === 0) {
    loopBox.appendChild(el("p", "empty", "PENDING Open Loop 없음"));
  } else {
    for (const loop of state.unresolved_open_loops) {
      const item = el("div", "item");
      item.appendChild(el("strong", null, `${loop.open_loop_id} · ${loop.topic_id || "-"}`));
      item.appendChild(el("div", null, loop.next_verification));
      loopBox.appendChild(item);
    }
  }
  const others = state.open_loops.filter((l) => l.state !== "PENDING");
  if (others.length > 0) {
    const done = el("div", "why", `그 외: ${others.map((l) => `${l.open_loop_id}=${l.state}`).join(", ")}`);
    loopBox.appendChild(done);
  }
  setPanel("p-loops", loopBox);

  const historyBox = el("div");
  if (state.inference_history.length === 0) {
    historyBox.appendChild(el("p", "empty", "변경 이력 없음"));
  } else {
    for (const revision of state.inference_history) {
      const item = el("div", "item");
      const before = revision.previous_inference ? revision.previous_inference.need_type : "(없음)";
      const after = revision.new_inference ? revision.new_inference.need_type : "(철회)";
      item.appendChild(el("strong", null, `${before} → ${after}`));
      item.appendChild(el("div", "why", revision.reason));
      item.appendChild(evidenceTags(revision.trigger_evidence));
      historyBox.appendChild(item);
    }
  }
  setPanel("p-history", historyBox);

  renderLoopOptions();
  renderVideoOptions();
}

/* ---------------- controls ---------------- */

function renderTopicSelect() {
  const select = document.getElementById("topic-select");
  select.innerHTML = "";
  for (const topic of store.topics) {
    const option = document.createElement("option");
    option.value = topic.topic_id;
    option.textContent = `${topic.topic_id} · ${topic.user_problem}`;
    if (topic.topic_id === store.activeTopicId) option.selected = true;
    select.appendChild(option);
  }
}

function renderLoopOptions() {
  const select = document.getElementById("event-loop");
  const previous = select.value;
  select.innerHTML = '<option value="">(없음)</option>';
  for (const loop of store.open_loops) {
    const option = document.createElement("option");
    option.value = loop.open_loop_id;
    option.textContent = `${loop.open_loop_id} · ${loop.topic_id || "-"} · ${loop.state}`;
    select.appendChild(option);
  }
  select.value = previous;
}

function renderVideoOptions() {
  const select = document.getElementById("video-compared-to");
  const previous = select.value;
  select.innerHTML = '<option value="">(없음)</option>';
  for (const video of store.video_evidence) {
    const option = document.createElement("option");
    option.value = video.analysis_id;
    option.textContent = `${video.analysis_id} · ${video.confidence}`;
    select.appendChild(option);
  }
  select.value = previous;
}

function wire() {
  document.getElementById("composer").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = document.getElementById("input");
    const text = input.value.trim();
    if (!text) return;
    store.messages.push({
      message_id: nextId("m"),
      role: "user",
      text,
      created_at: nowIso(),
      topic_id: store.activeTopicId,
    });
    input.value = "";
    save();
    renderMessages();
    await refresh(true);
  });

  document.getElementById("topic-select").addEventListener("change", async (event) => {
    store.activeTopicId = event.target.value;
    // 이전 상태는 다른 주제의 판정이다. 주제를 바꾸면 버린다.
    store.prior_state = null;
    save();
    if (store.messages.some((m) => m.role === "user")) await refresh(false);
    else renderMessages();
  });

  document.getElementById("new-topic").addEventListener("click", async () => {
    const problem = window.prompt("새 코칭 주제의 사용자 문제를 입력하세요");
    if (!problem) return;
    const topicId = `t${store.topics.length + 1}`;
    store.topics.push({ topic_id: topicId, user_problem: problem, root_problem: null });
    store.activeTopicId = topicId;
    store.prior_state = null;
    save();
    renderTopicSelect();
    if (store.messages.some((m) => m.role === "user")) await refresh(false);
  });

  document.getElementById("reset").addEventListener("click", () => {
    store = freshStore();
    lastState = null;
    save();
    renderTopicSelect();
    renderMessages();
    document.getElementById("panel-error").hidden = true;
    for (const id of ["p-topic", "p-intent", "p-needs", "p-engagement", "p-progress", "p-strategy", "p-evidence", "p-context", "p-loops", "p-history"]) {
      setPanel(id, el("p", "empty", "아직 없음"));
    }
    renderLoopOptions();
    renderVideoOptions();
  });

  document.getElementById("add-loop").addEventListener("click", async () => {
    const field = document.getElementById("loop-text");
    const text = field.value.trim();
    if (!text) return;
    store.open_loops.push({
      open_loop_id: nextId("ol"),
      topic_id: store.activeTopicId,
      next_verification: text,
      state: "PENDING",
      created_at: nowIso(),
    });
    field.value = "";
    save();
    renderLoopOptions();
    if (store.messages.some((m) => m.role === "user")) await refresh(false);
  });

  document.getElementById("add-event").addEventListener("click", async () => {
    const lastUser = [...store.messages].reverse().find((m) => m.role === "user");
    store.behavior_events.push({
      event_id: nextId("b"),
      event_type: document.getElementById("event-type").value,
      related_message_id: lastUser ? lastUser.message_id : null,
      created_at: nowIso(),
      topic_id: store.activeTopicId,
      open_loop_id: document.getElementById("event-loop").value || null,
    });
    save();
    if (store.messages.some((m) => m.role === "user")) await refresh(false);
  });

  document.getElementById("add-video").addEventListener("click", async () => {
    const field = document.getElementById("video-observation");
    const observation = field.value.trim();
    if (!observation) return;
    store.video_evidence.push({
      analysis_id: nextId("a"),
      observations: [observation],
      confidence: document.getElementById("video-confidence").value,
      source_frame_ids: [],
      comparison: document.getElementById("video-comparison").value,
      compared_to_analysis_id: document.getElementById("video-compared-to").value || null,
    });
    field.value = "";
    save();
    renderVideoOptions();
    if (store.messages.some((m) => m.role === "user")) await refresh(false);
  });
}

store = load();
renderTopicSelect();
renderMessages();
renderLoopOptions();
renderVideoOptions();
wire();
if (store.messages.some((m) => m.role === "user")) refresh(false);
