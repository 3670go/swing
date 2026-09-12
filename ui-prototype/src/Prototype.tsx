import {
  CameraIcon,
  CheckCircledIcon,
  Cross2Icon,
  ExclamationTriangleIcon,
  FileIcon,
  HamburgerMenuIcon,
  HandIcon,
  ImageIcon,
  InfoCircledIcon,
  Pencil2Icon,
  ReloadIcon,
  TargetIcon,
  TrashIcon,
  VideoIcon,
} from "@radix-ui/react-icons";
import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type CSSProperties,
} from "react";
import type { Session } from "@supabase/supabase-js";
import {
  BottomSheet,
  Carousel,
  KeyboardInput,
  MobileScroll,
  useKeyboard,
  useKeyboardInsets,
  useMobileDevice,
} from "./mobile";
import { authConfigured, supabase } from "./auth";

type MediaKind = "photo" | "video";
type AnalysisStatus =
  | "uploading"
  | "checking"
  | "queued"
  | "running"
  | "succeeded"
  | "limited"
  | "rejected"
  | "failed";

type MediaDraft = {
  id: string;
  kind: MediaKind;
  name: string;
  file: File;
  previewUrl: string;
  objectUrl: boolean;
};

type AnalysisMedia = Omit<MediaDraft, "file">;

type ObservationItemResponse = {
  timestamp: string | null;
  subject: string;
  reference: string;
  phase: string;
  state: string;
  assessment_category: string;
  confidence: number;
};

type VisionObservationResponse = {
  is_golf_media: boolean;
  golf_media_reason: string;
  observations: ObservationItemResponse[];
  cannot_determine: string[];
};

type CoachReplyResponse = {
  base_assessment: {
    primary_category: string;
    importance: "high" | "medium" | "low";
    findings: Array<{
      category: string;
      observation_indexes: number[];
      summary: string;
      confidence: number;
    }>;
    cannot_determine: string[];
    assessment_hash: string;
  };
  content: {
    direct_answer: string;
    causal_chain: string[];
    cannot_determine: string[];
    single_change: string | null;
    verification: string | null;
  };
  conversation: {
    message: string;
    positive_feedback: string | null;
    positive_topic: string | null;
    follow_up_question: string | null;
    question_topic: string | null;
    invite_mode: string;
  };
};

type AnalysisApiResponse = {
  conversation_id: string;
  analysis_run_id: string;
  status: "succeeded" | "limited" | "rejected";
  observation: VisionObservationResponse;
  reply: CoachReplyResponse | null;
};

type HistoryItemResponse = {
  analysis_run_id: string;
  status: string;
  media_kind: MediaKind;
  club: string;
  camera_view: "face_on" | "down_the_line";
  created_at: string;
};

type MemberProfileResponse = {
  owner_context_id: string;
  display_name: string | null;
  default_handedness: "right" | "left" | null;
  current_swing_style: string | null;
  target_swing_style: string | null;
  body_traits: Array<{ body_region: string | null; statement: string; expires_at: string | null }>;
  injuries: Array<{ body_region: string | null; statement: string; expires_at: string | null }>;
};

type RoadmapMilestoneResponse = {
  milestone_id: string;
  version: number;
  sort_order: number;
  title: string;
  evidence_level: string;
  completion_condition: string;
};

type RoadmapResponse = {
  roadmap_id: string;
  version: number;
  target_swing: string;
  starting_state: string | null;
  next_completion_condition: string | null;
  current_milestone: RoadmapMilestoneResponse | null;
  milestones: RoadmapMilestoneResponse[];
};

type ProfileForm = {
  displayName: string;
  handedness: "right" | "left";
  currentSwingStyle: string;
  targetSwingStyle: string;
  bodyTrait: string;
  injuryRegion: string;
  injury: string;
};

type ContextState = {
  shot: "풀스윙" | "숏게임";
  shortGame: "칩" | "피치" | "로브" | "그린사이드 벙커";
  club: string;
  angle: "정면" | "후방";
  handedness: "오른손" | "왼손";
  goal: "자세교정" | "샷 결과" | "비교";
  videoType: "일반 스윙" | "리드손 한손" | "트레일손 한손" | "기타 드릴";
  shotResult: string;
  comparison: string;
};

type ChatMessage = {
  id: number | string;
  role: "user" | "assistant";
  text: string;
};

type ConversationHistoryResponse = {
  conversation_id: string | null;
  messages: Array<{
    message_id: string;
    role: "user" | "assistant";
    content: string;
  }>;
};

type AnalysisRun = {
  id: string;
  analysisRunId?: string;
  status: AnalysisStatus;
  media: AnalysisMedia[];
  question: string;
  context: ContextState;
  result?: AnalysisApiResponse;
  error?: string;
};

const initialMessages: ChatMessage[] = [
  {
    id: 1,
    role: "assistant",
    text: "영상 없이 질문해도 됩니다. 현재 조건을 먼저 확인하고, 미디어가 없으면 확정할 수 없는 범위를 나눠서 답할게요.",
  },
];

const initialContext: ContextState = {
  shot: "풀스윙",
  shortGame: "칩",
  club: "7번 아이언",
  angle: "정면",
  handedness: "오른손",
  goal: "자세교정",
  videoType: "일반 스윙",
  shotResult: "",
  comparison: "최근 7번 아이언 · 정면",
};

const fullSwingClubs = [
  "드라이버",
  "3번 우드",
  "5번 우드",
  "하이브리드",
  "5번 아이언",
  "7번 아이언",
  "9번 아이언",
  "PW",
  "SW",
];
const shortGameClubs = ["9번 아이언", "PW", "GW", "SW", "LW"];
const pendingStatuses: AnalysisStatus[] = ["uploading", "checking", "queued", "running"];
const roadmapEvidenceLabels: Record<string, string> = {
  NOT_STARTED: "시작 전",
  USER_REPORTED_PROGRESS: "사용자 변화 보고",
  RESULT_REPEATED: "결과 반복 확인",
  VIDEO_VERIFIED_PROGRESS: "영상 변화 확인",
  MILESTONE_COMPLETED: "단계 완료",
};
const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8080").replace(/\/$/, "");

const statusCopy: Record<AnalysisStatus, { label: string; detail: string }> = {
  uploading: { label: "업로드 중", detail: "비공개 보관함으로 미디어를 보내고 있습니다." },
  checking: { label: "미디어 검사", detail: "골프 장면·파일 상태·촬영 조건을 확인합니다." },
  queued: { label: "분석 대기", detail: "분석 작업이 등록됐습니다. 채팅은 계속 사용할 수 있습니다." },
  running: { label: "영상 선관찰 중", detail: "질문과 느낌을 제외한 미디어 근거를 먼저 확인합니다." },
  succeeded: { label: "분석 완료", detail: "기본 판정을 고정한 뒤 질문과 대조했습니다." },
  limited: { label: "제한 분석 완료", detail: "확인 가능한 항목과 판정 불가 항목을 분리했습니다." },
  rejected: { label: "분석하지 않음", detail: "골프 스윙·숏게임 장면을 확인할 수 없습니다." },
  failed: { label: "분석 실패", detail: "분석 요청을 완료하지 못했습니다." },
};

function toApiContext(context: ContextState) {
  return {
    shot_profile: context.shot === "풀스윙" ? "full_swing" : "short_game",
    club: context.club,
    camera_view: context.angle === "정면" ? "face_on" : "down_the_line",
    handedness: context.handedness === "오른손" ? "right" : "left",
    analysis_goal: {
      자세교정: "posture_correction",
      "샷 결과": "shot_result",
      비교: "comparison",
    }[context.goal],
    short_game_type: context.shot === "숏게임" ? context.shortGame : null,
    video_type: context.videoType,
    shot_result: context.goal === "샷 결과" ? context.shotResult || null : null,
  };
}

async function apiErrorMessage(response: Response): Promise<string> {
  let detail = "";
  try {
    const payload = await response.json();
    detail = typeof payload.detail === "string" ? payload.detail : "";
  } catch {
    detail = "";
  }
  const known: Record<string, string> = {
    "GEMINI_API_KEY is not configured": "서버에 Gemini API 키가 설정되지 않았습니다.",
    MODEL_UNAVAILABLE: "AI 모델 응답을 받지 못했습니다. 잠시 후 다시 시도하세요.",
    MODEL_RATE_LIMITED: "Gemini 사용량 한도에 걸렸습니다. 잠시 후 다시 시도하세요.",
    MODEL_AUTH_FAILED: "Gemini API 키가 거부됐습니다. 서버 설정을 확인하세요.",
    MODEL_REQUEST_INVALID: "Gemini가 분석 요청 형식을 거부했습니다.",
    MODEL_PROVIDER_UNAVAILABLE: "Gemini 서비스가 일시적으로 응답하지 않습니다.",
    MODEL_RESPONSE_INVALID: "Gemini 응답이 분석 결과 형식 검사를 통과하지 못했습니다.",
    MODEL_OUTPUT_INVALID: "답변을 정리하는 중 문제가 생겼어요. 잠시 후 다시 보내주세요.",
    REQUEST_CONTRACT_INVALID: "대화 정보를 읽는 중 문제가 생겼어요. 잠시 후 다시 보내주세요.",
    COACHING_GUARD_REJECTED: "답변 근거를 확인하는 과정에서 멈췄어요. 잠시 후 다시 보내주세요.",
    ANALYSIS_CONTRACT_FAILED: "분석 근거를 확인하는 과정에서 멈췄어요. 잠시 후 다시 보내주세요.",
    INTERNAL_ERROR: "서버가 요청을 완료하지 못했어요. 잠시 후 다시 보내주세요.",
    STORAGE_UNAVAILABLE: "비공개 미디어 저장소에 연결하지 못했습니다.",
    MEDIA_DECODE_FAILED: "선택한 영상을 읽거나 프레임으로 변환하지 못했습니다.",
    MEDIA_TYPE_UNSUPPORTED: "지원하지 않는 파일 형식입니다.",
    MEDIA_EMPTY: "선택한 파일이 비어 있습니다.",
    VIDEO_TOO_LARGE: "허용된 영상 크기를 초과했습니다.",
    AUTHENTICATION_REQUIRED: "로그인이 필요한 기능입니다.",
    OWNER_CLAIM_CONFLICT: "이 브라우저의 익명 기록은 기존 회원 기록과 자동으로 합칠 수 없습니다.",
    ANALYSIS_NOT_FOUND: "이 계정에서 해당 분석을 찾을 수 없습니다.",
    ROADMAP_SOURCE_INCOMPLETE: "로드맵으로 만들 교정 한 가지와 확인 기준이 부족합니다.",
  };
  return known[detail] ?? `서버 요청을 완료하지 못했어요. 잠시 후 다시 보내주세요. (${response.status})`;
}

function requestFailureMessage(error: unknown, fallback: string): string {
  if (error instanceof TypeError && error.message.toLowerCase().includes("fetch")) {
    return "서버 연결이 잠시 끊겼어요. 잠시 후 다시 보내주세요.";
  }
  return error instanceof Error && error.message ? error.message : fallback;
}

function AssistantMark() {
  return (
    <span className="assistant-mark" aria-hidden="true">
      <TargetIcon width={18} height={18} />
    </span>
  );
}

function AnalysisCard({
  run,
  onDelete,
  onSaveRoadmap,
}: {
  run: AnalysisRun;
  onDelete: () => void;
  onSaveRoadmap: () => void;
}) {
  const copy = statusCopy[run.status];
  const isPending = pendingStatuses.includes(run.status);
  const mediaLabel = run.media.length === 1
    ? run.media[0].name
    : `${run.media[0].name} 외 ${run.media.length - 1}개`;
  const mediaKindLabel = run.media.every((item) => item.kind === "photo")
    ? `사진 ${run.media.length}개`
    : run.media.every((item) => item.kind === "video")
      ? `영상 ${run.media.length}개`
      : `사진·영상 ${run.media.length}개`;
  const progress = {
    uploading: 22,
    checking: 44,
    queued: 61,
    running: 82,
    succeeded: 100,
    limited: 100,
    rejected: 100,
    failed: 100,
  }[run.status];

  return (
    <article className={`analysis-card status-${run.status}`} aria-live="polite">
      <div className="analysis-card-heading">
        <div className="analysis-status-icon" aria-hidden="true">
          {run.status === "rejected" || run.status === "failed" ? (
            <ExclamationTriangleIcon />
          ) : run.status === "succeeded" || run.status === "limited" ? (
            <CheckCircledIcon />
          ) : (
            <ReloadIcon className={run.status === "running" ? "spin-icon" : ""} />
          )}
        </div>
        <div>
          <span>{copy.label}</span>
          <strong>{mediaLabel}</strong>
        </div>
        <small>{mediaKindLabel}</small>
      </div>

      <p className="analysis-status-detail">{copy.detail}</p>
      <div className="analysis-progress" aria-label={`분석 진행률 ${progress}%`}>
        <span style={{ width: `${progress}%` }} />
      </div>

      {isPending ? (
        <p className="pending-chat-note">분석을 기다리는 동안 아래 채팅을 계속 사용할 수 있습니다.</p>
      ) : null}

      {run.status === "rejected" ? (
        <div className="analysis-error-copy">
          <strong>골퍼와 클럽이 모두 보이는 미디어가 필요합니다.</strong>
          <span>{run.result?.observation.golf_media_reason ?? "이 파일로 골프 판정이나 교정 답변을 생성하지 않았습니다."}</span>
        </div>
      ) : null}

      {run.status === "failed" ? (
        <div className="analysis-error-copy">
          <strong>분석을 완료하지 못했습니다.</strong>
          <span>{run.error ?? "백엔드 연결과 설정을 확인한 뒤 다시 시도하세요."}</span>
        </div>
      ) : null}

      {(run.status === "succeeded" || run.status === "limited") && run.result?.reply ? (
        <div className={`result-summary ${run.status === "limited" ? "limited-result" : ""}`}>
          <div className="result-labels">
            <span>{run.status === "limited" ? "사진 기반" : run.context.goal}</span>
            <span>중요도 {run.result.reply.base_assessment.importance}</span>
          </div>
          <h3>{run.result.reply.conversation.message}</h3>
          {run.result.reply.conversation.positive_feedback ? (
            <p className="result-positive">{run.result.reply.conversation.positive_feedback}</p>
          ) : null}
          {run.result.reply.conversation.follow_up_question ? (
            <p className="result-follow-up">{run.result.reply.conversation.follow_up_question}</p>
          ) : null}

          <details className="analysis-evidence">
            <summary>분석 근거 보기</summary>
            <Carousel ariaLabel="근거 프레임" className="evidence-carousel" contentClassName="evidence-list">
            {run.media.map((item, index) => (
              <figure className="evidence-frame" key={item.id}>
                {item.kind === "video" ? (
                  <video src={item.previewUrl} muted playsInline controls preload="metadata" />
                ) : (
                  <img src={item.previewUrl} alt={`분석한 스윙 사진 ${index + 1}`} />
                )}
                <figcaption>원본 미디어 {index + 1}</figcaption>
              </figure>
            ))}
            {run.result.observation.observations.map((item, index) => (
              <figure key={`${item.timestamp ?? "frame"}-${index}`} className="evidence-text-frame">
                <strong>{item.phase}</strong>
                <span>{item.subject} · {item.reference}</span>
                <p>{item.state}</p>
                <figcaption>{item.timestamp ?? `관찰 ${index + 1}`}</figcaption>
              </figure>
            ))}
            </Carousel>

            <dl>
              <div><dt>우선 판정</dt><dd>{run.result.reply.base_assessment.findings.map((item) => item.summary).join(" ")}</dd></div>
              <div><dt>연결 해석</dt><dd>{run.result.reply.content.causal_chain.join(" ")}</dd></div>
              <div><dt>현재 확인 불가</dt><dd>{run.result.reply.content.cannot_determine.join(" · ")}</dd></div>
              {run.result.reply.content.single_change ? (
                <div className="single-change"><dt>이번에 바꿀 한 가지</dt><dd>{run.result.reply.content.single_change}</dd></div>
              ) : null}
              {run.result.reply.content.verification ? (
                <div><dt>다음 확인</dt><dd>{run.result.reply.content.verification}</dd></div>
              ) : null}
            </dl>
          </details>
          {run.result.reply.content.single_change && run.result.reply.content.verification ? (
            <button className="roadmap-save-action" type="button" onClick={onSaveRoadmap}>
              내 로드맵으로 저장
            </button>
          ) : null}
        </div>
      ) : null}

      {!isPending ? (
        <button className="delete-run" type="button" onClick={onDelete}>
          <TrashIcon /> 이 분석 삭제
        </button>
      ) : null}
    </article>
  );
}

export default function Prototype() {
  const keyboard = useKeyboard();
  const { bottomInset } = useKeyboardInsets();
  const { device } = useMobileDevice();
  const [messages, setMessages] = useState(initialMessages);
  const [drafts, setDrafts] = useState<MediaDraft[]>([]);
  const [activeRun, setActiveRun] = useState<AnalysisRun | null>(null);
  const [chatText, setChatText] = useState("");
  const [question, setQuestion] = useState("");
  const [context, setContext] = useState<ContextState>(initialContext);
  const [menuOpen, setMenuOpen] = useState(false);
  const [analysisOpen, setAnalysisOpen] = useState(false);
  const [contextOpen, setContextOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const [authOpen, setAuthOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [roadmapOpen, setRoadmapOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [analysisSubmitting, setAnalysisSubmitting] = useState(false);
  const [chatSubmitting, setChatSubmitting] = useState(false);
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [historyItems, setHistoryItems] = useState<HistoryItemResponse[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [session, setSession] = useState<Session | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "signup">("signup");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [memberSubmitting, setMemberSubmitting] = useState(false);
  const [memberRestoring, setMemberRestoring] = useState(false);
  const [profile, setProfile] = useState<MemberProfileResponse | null>(null);
  const [profileForm, setProfileForm] = useState<ProfileForm>({
    displayName: "",
    handedness: "right",
    currentSwingStyle: "",
    targetSwingStyle: "",
    bodyTrait: "",
    injuryRegion: "",
    injury: "",
  });
  const [activeRoadmap, setActiveRoadmap] = useState<RoadmapResponse | null>(null);
  const [roadmapSourceRunId, setRoadmapSourceRunId] = useState<string | null>(() =>
    window.localStorage.getItem("swing-analyzer-pending-roadmap-source"));
  const [roadmapTarget, setRoadmapTarget] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [anonymousSessionId, setAnonymousSessionId] = useState(() => {
    const storageKey = "swing-analyzer-anonymous-session";
    const existing = window.localStorage.getItem(storageKey);
    if (existing && existing.length >= 16) return existing;
    const generated = `${crypto.randomUUID()}-${crypto.randomUUID()}`;
    window.localStorage.setItem(storageKey, generated);
    return generated;
  });
  const mediaInputRef = useRef<HTMLInputElement>(null);
  const restoredAccessTokenRef = useRef<string | null>(null);

  const clubOptions = context.shot === "숏게임" ? shortGameClubs : fullSwingClubs;
  const runPending = Boolean(activeRun && pendingStatuses.includes(activeRun.status));

  useEffect(() => {
    if (!supabase) return;
    let mounted = true;
    void supabase.auth.getSession().then(({ data, error }) => {
      if (!mounted) return;
      if (error) {
        setNotice(error.message);
        return;
      }
      setSession(data.session);
      if (data.session) void restoreMemberState(data.session);
    });
    const { data: listener } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      if (!mounted) return;
      setSession(nextSession);
      if (nextSession) void restoreMemberState(nextSession);
      else {
        setProfile(null);
        setActiveRoadmap(null);
      }
    });
    return () => {
      mounted = false;
      listener.subscription.unsubscribe();
    };
  }, [anonymousSessionId]);

  function bearerHeaders(currentSession: Session | null = session): Record<string, string> {
    return currentSession ? { Authorization: `Bearer ${currentSession.access_token}` } : {};
  }

  async function restoreMemberState(currentSession: Session) {
    if (restoredAccessTokenRef.current === currentSession.access_token) return;
    restoredAccessTokenRef.current = currentSession.access_token;
    setMemberRestoring(true);
    try {
      const claimResponse = await fetch(`${apiBaseUrl}/v1/me/claim`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...bearerHeaders(currentSession),
        },
        body: JSON.stringify({ anonymous_session_id: anonymousSessionId }),
      });
      if (!claimResponse.ok && claimResponse.status !== 409) {
        throw new Error(await apiErrorMessage(claimResponse));
      }
      await Promise.all([
        loadLatestConversation(currentSession),
        loadMemberProfile(currentSession),
        loadActiveRoadmap(currentSession),
      ]);
      if (claimResponse.status === 409) {
        setNotice("로그인은 복원했지만 현재 익명 기록은 기존 회원 기록과 자동 병합하지 않았습니다.");
      } else {
        setNotice("회원 세션과 저장된 코칭 상태를 복원했습니다.");
      }
      if (roadmapSourceRunId) setRoadmapOpen(true);
    } catch (error) {
      restoredAccessTokenRef.current = null;
      setNotice(requestFailureMessage(error, "회원 상태를 복원하지 못했습니다."));
    } finally {
      setMemberRestoring(false);
    }
  }

  async function loadLatestConversation(currentSession: Session) {
    const query = new URLSearchParams({ anonymous_session_id: anonymousSessionId });
    const response = await fetch(`${apiBaseUrl}/v1/conversations/latest?${query}`, {
      headers: bearerHeaders(currentSession),
    });
    if (!response.ok) throw new Error(await apiErrorMessage(response));
    const restored = (await response.json()) as ConversationHistoryResponse;
    setConversationId(restored.conversation_id);
    setMessages(restored.messages.length > 0
      ? restored.messages.map((message) => ({
          id: message.message_id,
          role: message.role,
          text: message.content,
        }))
      : initialMessages);
  }

  async function loadMemberProfile(currentSession: Session = session!) {
    if (!currentSession) return;
    const response = await fetch(`${apiBaseUrl}/v1/me/profile`, {
      headers: bearerHeaders(currentSession),
    });
    if (!response.ok) throw new Error(await apiErrorMessage(response));
    const nextProfile = (await response.json()) as MemberProfileResponse;
    setProfile(nextProfile);
    setProfileForm({
      displayName: nextProfile.display_name ?? "",
      handedness: nextProfile.default_handedness ?? "right",
      currentSwingStyle: nextProfile.current_swing_style ?? "",
      targetSwingStyle: nextProfile.target_swing_style ?? "",
      bodyTrait: nextProfile.body_traits[0]?.statement ?? "",
      injuryRegion: nextProfile.injuries[0]?.body_region ?? "",
      injury: nextProfile.injuries[0]?.statement ?? "",
    });
    setRoadmapTarget((current) => current || nextProfile.target_swing_style || "");
    if (nextProfile.default_handedness) {
      setContext((current) => ({
        ...current,
        handedness: nextProfile.default_handedness === "right" ? "오른손" : "왼손",
      }));
    }
  }

  async function loadActiveRoadmap(currentSession: Session = session!) {
    if (!currentSession) return;
    const response = await fetch(`${apiBaseUrl}/v1/me/roadmaps/active`, {
      headers: bearerHeaders(currentSession),
    });
    if (!response.ok) throw new Error(await apiErrorMessage(response));
    const result = (await response.json()) as { roadmap: RoadmapResponse | null };
    setActiveRoadmap(result.roadmap);
  }

  async function submitMembership() {
    if (!supabase) {
      setNotice("Supabase URL과 publishable key를 설정해야 회원 기능을 사용할 수 있습니다.");
      return;
    }
    if (!email.trim() || password.length < 6) {
      setNotice("이메일과 6자 이상의 비밀번호를 입력하세요.");
      return;
    }
    setMemberSubmitting(true);
    try {
      const result = authMode === "signup"
        ? await supabase.auth.signUp({ email: email.trim(), password })
        : await supabase.auth.signInWithPassword({ email: email.trim(), password });
      if (result.error) throw result.error;
      if (!result.data.session) {
        setNotice("가입 확인 메일을 보냈습니다. 확인 후 로그인하세요.");
        setAuthMode("login");
        return;
      }
      setSession(result.data.session);
      setPassword("");
      setAuthOpen(false);
      await restoreMemberState(result.data.session);
      if (roadmapSourceRunId) setRoadmapOpen(true);
    } catch (error) {
      setNotice(requestFailureMessage(error, "회원 요청을 완료하지 못했습니다."));
    } finally {
      setMemberSubmitting(false);
    }
  }

  async function logout() {
    if (!supabase) return;
    const { error } = await supabase.auth.signOut();
    if (error) {
      setNotice(error.message);
      return;
    }
    const nextAnonymousSession = `${crypto.randomUUID()}-${crypto.randomUUID()}`;
    window.localStorage.setItem("swing-analyzer-anonymous-session", nextAnonymousSession);
    setAnonymousSessionId(nextAnonymousSession);
    window.localStorage.removeItem("swing-analyzer-pending-roadmap-source");
    restoredAccessTokenRef.current = null;
    revokeMedia(drafts);
    if (activeRun) revokeMedia(activeRun.media);
    setSession(null);
    setProfile(null);
    setActiveRoadmap(null);
    setConversationId(null);
    setMessages(initialMessages);
    setDrafts([]);
    setActiveRun(null);
    setMenuOpen(false);
    setNotice("로그아웃했습니다. 새 익명 세션으로 전환했습니다.");
  }

  async function saveProfile() {
    if (!session) return;
    setMemberSubmitting(true);
    try {
      const response = await fetch(`${apiBaseUrl}/v1/me/profile`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...bearerHeaders(),
        },
        body: JSON.stringify({
          display_name: profileForm.displayName || null,
          default_handedness: profileForm.handedness,
          current_swing_style: profileForm.currentSwingStyle || null,
          target_swing_style: profileForm.targetSwingStyle || null,
          body_traits: profileForm.bodyTrait
            ? [{ body_region: null, statement: profileForm.bodyTrait }]
            : [],
          injuries: profileForm.injury
            ? [{ body_region: profileForm.injuryRegion || null, statement: profileForm.injury }]
            : [],
        }),
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response));
      const nextProfile = (await response.json()) as MemberProfileResponse;
      setProfile(nextProfile);
      setProfileOpen(false);
      setNotice("장기 프로필을 저장했습니다.");
    } catch (error) {
      setNotice(requestFailureMessage(error, "프로필을 저장하지 못했습니다."));
    } finally {
      setMemberSubmitting(false);
    }
  }

  function beginRoadmap(run: AnalysisRun) {
    if (!run.analysisRunId) return;
    setRoadmapSourceRunId(run.analysisRunId);
    window.localStorage.setItem("swing-analyzer-pending-roadmap-source", run.analysisRunId);
    setRoadmapTarget(profile?.target_swing_style ?? "");
    if (!session) {
      setAuthMode("signup");
      setAuthOpen(true);
      setNotice("분석 결과를 장기 로드맵으로 저장하려면 가입하거나 로그인하세요.");
      return;
    }
    setRoadmapOpen(true);
  }

  async function createRoadmap() {
    if (!session || !roadmapSourceRunId || !roadmapTarget.trim()) {
      setNotice("목표 스윙을 입력하세요.");
      return;
    }
    setMemberSubmitting(true);
    try {
      const response = await fetch(`${apiBaseUrl}/v1/me/roadmaps`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...bearerHeaders(),
        },
        body: JSON.stringify({
          analysis_run_id: roadmapSourceRunId,
          target_swing: roadmapTarget.trim(),
        }),
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response));
      setActiveRoadmap((await response.json()) as RoadmapResponse);
      window.localStorage.removeItem("swing-analyzer-pending-roadmap-source");
      setRoadmapSourceRunId(null);
      setRoadmapOpen(false);
      setNotice("개인 스윙 로드맵을 저장했습니다.");
    } catch (error) {
      setNotice(requestFailureMessage(error, "로드맵을 저장하지 못했습니다."));
    } finally {
      setMemberSubmitting(false);
    }
  }

  function revokeMedia(items: Array<MediaDraft | AnalysisMedia>) {
    items.forEach((item) => {
      if (item.objectUrl) URL.revokeObjectURL(item.previewUrl);
    });
  }

  function removeDraft(draftId: string) {
    setDrafts((current) => {
      const removed = current.find((item) => item.id === draftId);
      if (removed) revokeMedia([removed]);
      return current.filter((item) => item.id !== draftId);
    });
  }

  function openAnalysis() {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    keyboard.hide();
    window.requestAnimationFrame(() => setAnalysisOpen(true));
  }

  function closeAnalysis() {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    keyboard.hide();
    setAnalysisOpen(false);
  }

  function handleFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    if (files.length === 0) return;
    const nextDrafts = files.flatMap((file): MediaDraft[] => {
      const kind = file.type.startsWith("image/")
        ? "photo"
        : file.type.startsWith("video/")
          ? "video"
          : null;
      if (!kind) return [];
      return [{
        id: crypto.randomUUID(),
        kind,
        name: file.name,
        file,
        previewUrl: URL.createObjectURL(file),
        objectUrl: true,
      }];
    });
    if (nextDrafts.length === 0) {
      setNotice("지원되는 사진 또는 영상을 선택하세요.");
      event.target.value = "";
      return;
    }
    setDrafts((current) => [...current, ...nextDrafts]);
    setNotice(`사진·영상 ${nextDrafts.length}개를 미디어 초안에 추가했습니다.`);
    setAnalysisOpen(true);
    event.target.value = "";
  }

  function validateAnalysisInput() {
    if (drafts.length === 0) return "사진 또는 영상을 한 개 이상 추가하세요.";
    if (context.goal === "샷 결과" && !context.shotResult) return "샷 결과를 하나 선택하세요.";
    if (context.goal === "비교" && !context.comparison) return "비교할 이전 분석을 선택하세요.";
    return null;
  }

  async function submitAnalysis() {
    if (memberRestoring) return;
    const validationMessage = validateAnalysisInput();
    if (validationMessage) {
      setNotice(validationMessage);
      if (drafts.length > 0) setContextOpen(true);
      return;
    }
    if (drafts.length === 0) return;

    const submittedDrafts = drafts;
    const runId = `run-${Date.now()}`;
    const submittedQuestion = question.trim() || "전체 우선순위로 분석해줘";
    const baseRun: AnalysisRun = {
      id: runId,
      status: "uploading",
      media: submittedDrafts.map(({ file: _file, ...item }) => item),
      question: question.trim(),
      context: { ...context },
    };

    keyboard.hide();
    setAnalysisSubmitting(true);
    setActiveRun(baseRun);
    setMessages((current) => [...current, { id: Date.now(), role: "user", text: submittedQuestion }]);
    setDrafts([]);
    setQuestion("");
    setAnalysisOpen(false);
    setNotice("미디어 업로드를 시작했습니다. 채팅은 계속 사용할 수 있습니다.");

    const formData = new FormData();
    submittedDrafts.forEach((item) => formData.append("files", item.file));
    formData.append("anonymous_session_id", anonymousSessionId);
    formData.append("context_json", JSON.stringify(toApiContext(context)));
    formData.append("question", question.trim());
    if (conversationId) formData.append("conversation_id", conversationId);

    setActiveRun((current) => (current?.id === runId ? { ...current, status: "running" } : current));
    try {
      const response = await fetch(`${apiBaseUrl}/v1/analyze`, {
        method: "POST",
        headers: bearerHeaders(),
        body: formData,
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response));
      const result = (await response.json()) as AnalysisApiResponse;
      setConversationId(result.conversation_id);
      setActiveRun((current) =>
        current?.id === runId
          ? {
              ...current,
              id: result.analysis_run_id,
              analysisRunId: result.analysis_run_id,
              status: result.status,
              result,
            }
          : current,
      );
      setNotice(
        result.status === "rejected"
          ? "골프 장면을 확인할 수 없어 분석하지 않았습니다."
          : result.status === "limited"
            ? "사진에서 확인 가능한 범위만 분석했습니다."
            : "분석 결과가 같은 대화에 추가됐습니다.",
      );
    } catch (error) {
      const message = requestFailureMessage(error, "백엔드에 연결할 수 없습니다.");
      setActiveRun((current) =>
        current?.id === runId ? { ...current, status: "failed", error: message } : current,
      );
      setNotice(message);
    } finally {
      setAnalysisSubmitting(false);
    }
  }

  async function submitTextQuestion() {
    if (memberRestoring) return;
    const trimmed = chatText.trim();
    if (!trimmed) return;
    keyboard.hide();
    setChatSubmitting(true);
    setMessages((current) => [...current, { id: Date.now(), role: "user", text: trimmed }]);
    setChatText("");

    try {
      const response = await fetch(`${apiBaseUrl}/v1/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...bearerHeaders() },
        body: JSON.stringify({
          anonymous_session_id: anonymousSessionId,
          conversation_id: conversationId,
          message: trimmed,
          context: toApiContext(context),
        }),
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response));
      const result = (await response.json()) as { conversation_id: string; reply: string };
      setConversationId(result.conversation_id);
      setMessages((current) => [
        ...current,
        { id: Date.now() + 1, role: "assistant", text: result.reply },
      ]);
      setNotice("백엔드 답변을 받았습니다.");
    } catch (error) {
      const message = error instanceof Error && error.message
        ? error.message
        : "백엔드에 연결할 수 없습니다.";
      setMessages((current) => [
        ...current,
        { id: Date.now() + 1, role: "assistant", text: `답변 실패: ${message}` },
      ]);
      setNotice(message);
    } finally {
      setChatSubmitting(false);
    }
  }

  function resetConversation() {
    revokeMedia(drafts);
    if (activeRun) revokeMedia(activeRun.media);
    setMessages([]);
    setDrafts([]);
    setActiveRun(null);
    setChatText("");
    setQuestion("");
    setConversationId(null);
    setMenuOpen(false);
    setAnalysisOpen(false);
    setNotice("새 대화를 시작했습니다.");
  }

  async function loadHistory() {
    setHistoryLoading(true);
    try {
      const query = new URLSearchParams({ anonymous_session_id: anonymousSessionId });
      const response = await fetch(`${apiBaseUrl}/v1/history?${query}`, {
        headers: bearerHeaders(),
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response));
      const result = (await response.json()) as { items: HistoryItemResponse[] };
      setHistoryItems(result.items);
    } catch (error) {
      const message = error instanceof Error && error.message
        ? error.message
        : "분석 기록을 불러오지 못했습니다.";
      setNotice(message);
    } finally {
      setHistoryLoading(false);
    }
  }

  function openSecondarySheet(sheet: "history" | "guide") {
    setMenuOpen(false);
    window.requestAnimationFrame(() => {
      if (sheet === "history") {
        setHistoryOpen(true);
        void loadHistory();
      } else setGuideOpen(true);
    });
  }

  async function confirmDeleteRun() {
    if (!activeRun) return;
    setDeleteSubmitting(true);
    try {
      if (activeRun.analysisRunId) {
        const query = new URLSearchParams({ anonymous_session_id: anonymousSessionId });
        const response = await fetch(
          `${apiBaseUrl}/v1/analysis/${activeRun.analysisRunId}?${query}`,
          { method: "DELETE", headers: bearerHeaders() },
        );
        if (!response.ok) throw new Error(await apiErrorMessage(response));
      }
      revokeMedia(activeRun.media);
      setActiveRun(null);
      setDeleteOpen(false);
      setNotice("원본 미디어와 분석 결과를 삭제했습니다.");
    } catch (error) {
      const message = error instanceof Error && error.message
        ? error.message
        : "분석을 삭제하지 못했습니다.";
      setNotice(message);
    } finally {
      setDeleteSubmitting(false);
    }
  }

  function chooseShot(nextShot: ContextState["shot"]) {
    setContext((current) => ({
      ...current,
      shot: nextShot,
      club: nextShot === "숏게임" ? "SW" : current.club === "SW" ? "7번 아이언" : current.club,
    }));
  }

  return (
    <>
      <MobileScroll key={analysisOpen ? "analysis" : "chat"} className={`app-screen prototype-screen ${analysisOpen ? "analysis-open" : "chat-only"}`}>
        <main className="prototype-content" aria-label="AI 골프 코치 채팅" style={{ "--prototype-safe-top": `${device.geometry.safeArea.top}px`, "--chat-composer-bottom": `${bottomInset}px` } as CSSProperties}>
          <header className="chat-header">
            <button className="icon-button" type="button" aria-label="메뉴 열기" onClick={() => setMenuOpen(true)}><HamburgerMenuIcon width={22} height={22} /></button>
            <div className="header-copy">
              <strong>AI 골프 스윙 코치</strong>
              <span>{analysisOpen
                ? "미디어 분석 준비"
                : runPending
                  ? "분석 중 · 채팅 가능"
                  : session
                    ? memberRestoring
                      ? "회원 코칭 복원 중"
                      : `${profile?.display_name ?? session.user.email ?? "회원"} · 코칭 복원됨`
                    : "채팅 · 가입 전 사용 가능"}</span>
            </div>
            <span className="brand-mark" aria-label="골프 코치"><TargetIcon width={20} height={20} /></span>
          </header>

          <section className="conversation" aria-label="대화 내용">
            {messages.length === 0 ? (
              <div className="empty-chat"><TargetIcon width={22} height={22} /><strong>무엇이 궁금한가요?</strong><span>영상 없이 질문하거나 사진·영상을 추가하세요.</span></div>
            ) : messages.map((message) => (
              <article key={message.id} className={`message-row ${message.role}`}>
                {message.role === "assistant" ? <AssistantMark /> : null}<p>{message.text}</p>
              </article>
            ))}
            {activeRun ? (
              <AnalysisCard
                run={activeRun}
                onDelete={() => setDeleteOpen(true)}
                onSaveRoadmap={() => beginRoadmap(activeRun)}
              />
            ) : null}
          </section>

          {analysisOpen ? (
            <section className="media-draft" aria-labelledby="media-draft-title">
              <div className="draft-heading">
                <div><h2 id="media-draft-title">미디어 초안</h2><span>{drafts.length}</span></div>
                <button type="button" className="quiet-button" onClick={closeAnalysis}><Cross2Icon /> 닫기</button>
              </div>

              {drafts.length > 0 ? (
                <Carousel ariaLabel="첨부한 사진과 영상" className="draft-media-carousel" contentClassName="draft-media-list">
                  {drafts.map((item, index) => (
                    <article className="draft-media-item" key={item.id}>
                      <div className="media-preview">
                        {item.kind === "video" ? <video src={item.previewUrl} controls playsInline aria-label={item.name} /> : <img src={item.previewUrl} alt={`스윙 사진 미리보기 ${index + 1}`} />}
                        <span className="duration-badge">{item.kind === "video" ? "영상" : "사진 · 제한 분석"}</span>
                      </div>
                      <button type="button" className="remove-draft" onClick={() => removeDraft(item.id)}><TrashIcon width={16} height={16} />삭제</button>
                    </article>
                  ))}
                </Carousel>
              ) : (
                <div className="empty-draft"><ImageIcon width={22} height={22} /><span>사진 또는 영상을 한 개 이상 추가하세요.</span></div>
              )}

              <div className="media-source-section">
                <button className="media-attach-button" type="button" onClick={() => mediaInputRef.current?.click()}><ImageIcon width={20} height={20} /><span>사진·영상 첨부</span><small>여러 파일 선택 가능</small></button>
              </div>

              <label className="question-field">
                <span>질문 <small>(선택)</small></span>
                <div>
                  <KeyboardInput value={question} onChange={(event) => setQuestion(event.target.value)} onBlur={() => keyboard.hide()} placeholder="궁금한 점이나 느낌을 입력하세요" aria-label="질문 입력" />
                  {question ? <button type="button" aria-label="질문 지우기" onClick={() => setQuestion("")}><Cross2Icon /></button> : null}
                </div>
              </label>

              <div className="context-heading">
                <div><h3>상황 정보</h3><span>분석 전에 선택</span></div>
                <button type="button" onClick={() => setContextOpen(true)}>편집 <Pencil2Icon /></button>
              </div>

              <Carousel ariaLabel="분석 상황 정보" className="context-carousel" contentClassName="context-chip-list">
                <button type="button" className="context-chip" onClick={() => setContextOpen(true)}><TargetIcon /><span>스윙 종류<strong>{context.shot}</strong></span></button>
                <button type="button" className="context-chip" onClick={() => setContextOpen(true)}><FileIcon /><span>클럽<strong>{context.club}</strong></span></button>
                <button type="button" className="context-chip" onClick={() => setContextOpen(true)}><CameraIcon /><span>촬영 각도<strong>{context.angle}</strong></span></button>
                <button type="button" className="context-chip" onClick={() => setContextOpen(true)}><HandIcon /><span>사용 손<strong>{context.handedness}</strong></span></button>
                <button type="button" className="context-chip" onClick={() => setContextOpen(true)}><TargetIcon /><span>목적<strong>{context.goal}</strong></span></button>
              </Carousel>

              <p className="analysis-note"><InfoCircledIcon width={15} height={15} />미디어를 질문과 분리해 먼저 관찰한 뒤 답변에서 대조합니다.</p>
              {drafts.some((item) => item.kind === "photo") ? <p className="photo-limit-note">사진은 위치만 확인하며 동작 순서·템포의 단독 근거로 사용하지 않습니다.</p> : null}
              {notice ? <p className="status-notice" role="status">{notice}</p> : null}
              <div className="submit-actions"><button type="button" className="primary-action" disabled={drafts.length === 0 || analysisSubmitting || memberRestoring} onClick={submitAnalysis}>{analysisSubmitting ? "분석 요청 중…" : memberRestoring ? "회원 기록 복원 중…" : "분석 시작"}</button></div>
            </section>
          ) : null}
        </main>
      </MobileScroll>

      {!analysisOpen ? (
        <section className="chat-composer" aria-label="채팅 입력" style={{ "--chat-composer-bottom": `${bottomInset}px` } as CSSProperties}>
          {notice ? <p className="composer-status" role="status">{notice}</p> : null}
          <button className="composer-context" type="button" onClick={() => setContextOpen(true)}><span>현재 조건</span><strong>{context.shot} · {context.club} · {context.goal}</strong><Pencil2Icon /></button>
          <div className="composer-row">
            <button className="analysis-launch" type="button" disabled={runPending || memberRestoring} onPointerDown={(event) => event.preventDefault()} onClick={openAnalysis}><VideoIcon width={17} height={17} />분석</button>
            <KeyboardInput value={chatText} onChange={(event) => setChatText(event.target.value)} onBlur={() => keyboard.hide()} onKeyDown={(event) => { if (event.key === "Enter" && !event.nativeEvent.isComposing) submitTextQuestion(); }} placeholder="골프 스윙에 대해 질문하세요" aria-label="채팅 메시지 입력" />
            <button className="send-message" type="button" disabled={!chatText.trim() || chatSubmitting || memberRestoring} onPointerDown={(event) => event.preventDefault()} onClick={submitTextQuestion}>{chatSubmitting ? "전송 중" : memberRestoring ? "복원 중" : "전송"}</button>
          </div>
        </section>
      ) : null}

      <input ref={mediaInputRef} className="visually-hidden" type="file" accept="image/*,video/*" multiple onChange={handleFiles} />

      <BottomSheet open={menuOpen} onOpenChange={setMenuOpen} title="채팅 메뉴" description="대화, 회원 프로필과 코칭 기록을 관리합니다." snap={0.58}>
        <div className="sheet-action-list">
          {session ? (
            <>
              <p className="member-menu-state"><strong>{profile?.display_name ?? session.user.email}</strong><span>재로그인하면 같은 프로필과 로드맵을 복원합니다.</span></p>
              <button type="button" disabled={memberRestoring} onClick={() => { setMenuOpen(false); setProfileOpen(true); }}>장기 프로필 편집</button>
              <button type="button" disabled={memberRestoring} onClick={() => { setMenuOpen(false); setRoadmapSourceRunId(null); window.localStorage.removeItem("swing-analyzer-pending-roadmap-source"); setRoadmapOpen(true); void loadActiveRoadmap(); }}>내 스윙 로드맵</button>
              <button type="button" onClick={() => void logout()}>로그아웃</button>
            </>
          ) : (
            <button type="button" onClick={() => { setMenuOpen(false); setAuthOpen(true); }}>가입 · 로그인</button>
          )}
          <button type="button" onClick={resetConversation}>새 대화 시작</button>
          <button type="button" onClick={() => openSecondarySheet("history")}>분석 기록 보기</button>
          <button type="button" onClick={() => openSecondarySheet("guide")}>촬영 가이드</button>
        </div>
      </BottomSheet>

      <BottomSheet
        open={authOpen}
        onOpenChange={setAuthOpen}
        title={authMode === "signup" ? "회원가입" : "로그인"}
        description="가입 전 대화와 분석을 이 계정의 장기 코칭 기록으로 이어갑니다."
        snap={0.62}
      >
        <div className="member-form">
          {!authConfigured ? <p className="member-config-warning">VITE_SUPABASE_URL과 VITE_SUPABASE_PUBLISHABLE_KEY 설정이 필요합니다.</p> : null}
          <label><span>이메일</span><KeyboardInput type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="golfer@example.com" /></label>
          <label><span>비밀번호</span><KeyboardInput type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="6자 이상" /></label>
          <button className="sheet-primary" type="button" disabled={memberSubmitting || !authConfigured} onClick={() => void submitMembership()}>
            {memberSubmitting ? "처리 중…" : authMode === "signup" ? "가입하고 기록 이어가기" : "로그인하고 로드맵 복원"}
          </button>
          <button className="member-mode-switch" type="button" onClick={() => setAuthMode((current) => current === "signup" ? "login" : "signup")}>
            {authMode === "signup" ? "이미 계정이 있어요 · 로그인" : "처음이에요 · 회원가입"}
          </button>
        </div>
      </BottomSheet>

      <BottomSheet
        open={profileOpen}
        onOpenChange={setProfileOpen}
        title="장기 골프 프로필"
        description="다음 채팅과 분석에서 다시 참고할 회원 정보입니다."
        snap={0.86}
      >
        <div className="member-form">
          <label><span>표시 이름</span><KeyboardInput value={profileForm.displayName} onChange={(event) => setProfileForm((current) => ({ ...current, displayName: event.target.value }))} placeholder="예: 홍길동" /></label>
          <label><span>주로 사용하는 손</span><select value={profileForm.handedness} onChange={(event) => setProfileForm((current) => ({ ...current, handedness: event.target.value as "right" | "left" }))}><option value="right">오른손</option><option value="left">왼손</option></select></label>
          <label><span>현재 스윙 성향</span><KeyboardInput value={profileForm.currentSwingStyle} onChange={(event) => setProfileForm((current) => ({ ...current, currentSwingStyle: event.target.value }))} placeholder="예: 페이드가 자주 남" /></label>
          <label><span>목표 스윙</span><KeyboardInput value={profileForm.targetSwingStyle} onChange={(event) => setProfileForm((current) => ({ ...current, targetSwingStyle: event.target.value }))} placeholder="예: 일관된 스트레이트 구질" /></label>
          <label><span>신체 특성</span><KeyboardInput value={profileForm.bodyTrait} onChange={(event) => setProfileForm((current) => ({ ...current, bodyTrait: event.target.value }))} placeholder="예: 상체 회전이 빠른 편" /></label>
          <div className="member-inline-fields">
            <label><span>부상 부위</span><KeyboardInput value={profileForm.injuryRegion} onChange={(event) => setProfileForm((current) => ({ ...current, injuryRegion: event.target.value }))} placeholder="예: 왼쪽 손목" /></label>
            <label><span>현재 상태</span><KeyboardInput value={profileForm.injury} onChange={(event) => setProfileForm((current) => ({ ...current, injury: event.target.value }))} placeholder="없으면 비워두기" /></label>
          </div>
          <p className="member-form-note">부상 정보는 마지막 저장 후 90일 동안만 코칭 맥락에 포함됩니다.</p>
          <button className="sheet-primary" type="button" disabled={memberSubmitting || memberRestoring} onClick={() => void saveProfile()}>{memberSubmitting ? "저장 중…" : "프로필 저장"}</button>
        </div>
      </BottomSheet>

      <BottomSheet
        open={roadmapOpen}
        onOpenChange={setRoadmapOpen}
        title={roadmapSourceRunId ? "로드맵으로 저장" : "내 스윙 로드맵"}
        description={roadmapSourceRunId ? "방금 분석의 한 가지 교정과 확인 기준으로 첫 단계를 만듭니다." : "재로그인해도 이어지는 현재 목표와 검증 단계입니다."}
        snap={0.72}
      >
        {roadmapSourceRunId ? (
          <div className="member-form">
            <label><span>목표 스윙</span><KeyboardInput value={roadmapTarget} onChange={(event) => setRoadmapTarget(event.target.value)} placeholder="예: 일관된 스트레이트 구질" /></label>
            <button className="sheet-primary" type="button" disabled={memberSubmitting || memberRestoring || !roadmapTarget.trim()} onClick={() => void createRoadmap()}>{memberSubmitting ? "저장 중…" : memberRestoring ? "복원 중…" : "개인 로드맵 만들기"}</button>
          </div>
        ) : activeRoadmap ? (
          <article className="roadmap-card">
            <span>현재 목표</span><h3>{activeRoadmap.target_swing}</h3>
            {activeRoadmap.starting_state ? <p>{activeRoadmap.starting_state}</p> : null}
            {activeRoadmap.current_milestone ? (
              <div className="roadmap-milestone">
                <small>{roadmapEvidenceLabels[activeRoadmap.current_milestone.evidence_level] ?? activeRoadmap.current_milestone.evidence_level}</small>
                <strong>{activeRoadmap.current_milestone.title}</strong>
                <p>{activeRoadmap.current_milestone.completion_condition}</p>
              </div>
            ) : null}
          </article>
        ) : (
          <p className="sheet-empty">저장된 활성 로드맵이 없습니다. 분석 결과에서 만들 수 있습니다.</p>
        )}
      </BottomSheet>

      <BottomSheet open={contextOpen} onOpenChange={setContextOpen} title="상황 정보 편집" description="되묻지 않도록 분석 전에 필요한 정보를 선택합니다." snap={0.84}>
        <div className="context-editor">
          <fieldset><legend>스윙 종류</legend><div>{(["풀스윙", "숏게임"] as const).map((option) => <button key={option} type="button" className={context.shot === option ? "selected" : ""} onClick={() => chooseShot(option)}>{option}</button>)}</div></fieldset>
          {context.shot === "숏게임" ? <fieldset><legend>숏게임 유형</legend><div>{(["칩", "피치", "로브", "그린사이드 벙커"] as const).map((option) => <button key={option} type="button" className={context.shortGame === option ? "selected" : ""} onClick={() => setContext((current) => ({ ...current, shortGame: option }))}>{option}</button>)}</div></fieldset> : null}
          <fieldset><legend>클럽</legend><div>{clubOptions.map((option) => <button key={option} type="button" className={context.club === option ? "selected" : ""} onClick={() => setContext((current) => ({ ...current, club: option }))}>{option}</button>)}</div></fieldset>
          <fieldset><legend>촬영 각도</legend><div>{(["정면", "후방"] as const).map((option) => <button key={option} type="button" className={context.angle === option ? "selected" : ""} onClick={() => setContext((current) => ({ ...current, angle: option }))}>{option}</button>)}</div></fieldset>
          <fieldset><legend>주로 사용하는 손</legend><div>{(["오른손", "왼손"] as const).map((option) => <button key={option} type="button" className={context.handedness === option ? "selected" : ""} onClick={() => setContext((current) => ({ ...current, handedness: option }))}>{option}</button>)}</div></fieldset>
          <fieldset><legend>분석 목적</legend><div>{(["자세교정", "샷 결과", "비교"] as const).map((option) => <button key={option} type="button" className={context.goal === option ? "selected" : ""} onClick={() => setContext((current) => ({ ...current, goal: option }))}>{option}</button>)}</div></fieldset>
          {context.goal === "샷 결과" ? <fieldset><legend>이번 샷 결과</legend><div>{["왼쪽 출발", "오른쪽 출발", "슬라이스", "훅", "뒤땅", "탑핑"].map((option) => <button key={option} type="button" className={context.shotResult === option ? "selected" : ""} onClick={() => setContext((current) => ({ ...current, shotResult: option }))}>{option}</button>)}</div></fieldset> : null}
          {context.goal === "비교" ? <fieldset><legend>비교할 이전 분석</legend><div>{["최근 7번 아이언 · 정면", "지난 드라이버 · 후방"].map((option) => <button key={option} type="button" className={context.comparison === option ? "selected" : ""} onClick={() => setContext((current) => ({ ...current, comparison: option }))}>{option}</button>)}</div></fieldset> : null}
          <fieldset><legend>영상 유형</legend><div>{(["일반 스윙", "리드손 한손", "트레일손 한손", "기타 드릴"] as const).map((option) => <button key={option} type="button" className={context.videoType === option ? "selected" : ""} onClick={() => setContext((current) => ({ ...current, videoType: option }))}>{option}</button>)}</div></fieldset>
          <button className="sheet-primary" type="button" onClick={() => setContextOpen(false)}>선택 완료</button>
        </div>
      </BottomSheet>

      <BottomSheet open={historyOpen} onOpenChange={setHistoryOpen} title="분석 기록" description={session ? "현재 회원 계정에 저장된 분석입니다." : "현재 익명 세션에 저장된 분석입니다."} snap={0.64}>
        <div className="history-list">
          {historyLoading ? <p className="sheet-empty">분석 기록을 불러오는 중입니다.</p> : null}
          {!historyLoading && historyItems.length === 0 ? <p className="sheet-empty">저장된 분석이 없습니다.</p> : null}
          {historyItems.map((item) => {
            const date = new Intl.DateTimeFormat("ko-KR", { month: "short", day: "numeric" }).format(new Date(item.created_at));
            const angle = item.camera_view === "face_on" ? "정면" : "후방";
            return (
              <button key={item.analysis_run_id} type="button" onClick={() => { setHistoryOpen(false); setContext((current) => ({ ...current, comparison: `${item.club} · ${angle}` })); setNotice(`${item.club} · ${angle} 분석을 비교 후보로 선택했습니다.`); }}>
                <span>{date}</span><strong>{item.club} · {angle}</strong><small>{item.media_kind === "photo" ? "사진" : "영상"} · {item.status}</small>
              </button>
            );
          })}
        </div>
      </BottomSheet>

      <BottomSheet open={guideOpen} onOpenChange={setGuideOpen} title="촬영 가이드" description="기기 기본 카메라에서 아래 조건으로 촬영합니다." snap={0.58}>
        <ol className="capture-guide">
          <li><strong>한 번의 샷만</strong><span>어드레스부터 피니시까지 한 번만 담습니다.</span></li>
          <li><strong>카메라 고정</strong><span>전신과 클럽이 프레임 밖으로 나가지 않게 둡니다.</span></li>
          <li><strong>각도 선택</strong><span>정면 또는 후방 중 실제 촬영 위치와 같은 값을 고릅니다.</span></li>
        </ol>
        <button className="sheet-primary" type="button" onClick={() => { setGuideOpen(false); mediaInputRef.current?.click(); }}>사진·영상 첨부</button>
      </BottomSheet>

      <BottomSheet open={deleteOpen} onOpenChange={setDeleteOpen} title="분석을 삭제할까요?" description="원본 미디어와 파생 프레임도 함께 삭제되며 복구할 수 없습니다." snap={0.42}>
        <div className="delete-confirmation"><p>삭제 후 이 결과는 채팅·비교·근거 검색에 다시 사용되지 않습니다.</p><button type="button" className="danger-action" disabled={deleteSubmitting} onClick={confirmDeleteRun}>{deleteSubmitting ? "삭제 중…" : "영구 삭제"}</button><button type="button" disabled={deleteSubmitting} onClick={() => setDeleteOpen(false)}>취소</button></div>
      </BottomSheet>
    </>
  );
}
