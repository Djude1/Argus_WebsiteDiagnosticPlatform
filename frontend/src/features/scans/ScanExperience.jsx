import { useEffect, useMemo, useRef, useState } from "react";
import {
  Link,
  NavLink,
  Outlet,
  useOutletContext,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import ReactFlow, {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
} from "reactflow";
import "reactflow/dist/style.css";

import { api, fetchVerifiedDomains } from "../../api";
import { formatDateTime } from "../../shared/formatters";
import argusEyeStill from "../../assets/argus-eye-still.webp";
import argusEye from "../../assets/argus-eye.webp";
import PageRebuildPanel from "../../components/scans/PageRebuildPanel.jsx";
import { ScanStatusBadge, ScoreBadge } from "../../components/scans/ScanBadges.jsx";
import FixOutputSection from "../../components/scans/FixOutputSection.jsx";
import { useArgusStore } from "../../store";
import {
  CATEGORY_COLOR,
  CATEGORY_FILTERS,
  CATEGORY_LABELS,
  SEVERITY_FILTERS,
  SEVERITY_LABEL,
  apiErrorMessage,
  isInProgress,
  SeverityBarChart,
  StackedBar,
  StatusAgentGlyph,
  StatusCrawlGlyph,
  StatusDoneGlyph,
  StatusQueuedGlyph,
  StatusScanGlyph,
  useConfirmDialogs,
} from "../../shared/AppShared.jsx";

const SCAN_POLL_INTERVAL_MS = 2000;
const LIST_POLL_INTERVAL_MS = 3000;
const MAX_SITE_SCAN_PAGES = 50;
// 整站走訪深度（與後端 ARGUS_DEFAULT_MAX_DEPTH 一致）；頁數上限才是實際範圍，後端另讀 sitemap 補種子
const SITE_SCAN_DEPTH = 6;

// 掃描維度選項（value 必須與後端 ALL_CATEGORIES 一致）
const SCAN_CATEGORY_OPTIONS = [
  { value: "seo", label: "SEO", desc: "搜尋引擎優化" },
  { value: "aeo", label: "AEO", desc: "AI 答案引擎可讀性" },
  { value: "geo", label: "GEO", desc: "生成式搜尋整備" },
  { value: "ux", label: "UX", desc: "行動版版面" },
  { value: "security", label: "資安檢測", desc: "被動資安；主動測試必勾" },
];
const DEFAULT_SCAN_CATEGORIES = SCAN_CATEGORY_OPTIONS.map((option) => option.value);

// localStorage 暫存表單草稿的 key
const SCAN_DRAFT_KEY = "argus_scan_draft_v1";

// ============================================================
// 通用小元件
// ============================================================

// 舊任務（progress 沒有 steps）的四階段進度條：等待 → 爬取 → 掃描 → Agent 測試
const CRAWL_PHASES = [
  { key: "queued", label: "等待", Icon: StatusQueuedGlyph },
  { key: "crawling", label: "爬取", Icon: StatusCrawlGlyph },
  { key: "scanning", label: "掃描", Icon: StatusScanGlyph },
  { key: "agent_testing", label: "Agent", Icon: StatusAgentGlyph },
];

// 細分階段（後端 progress.steps／progress.step，見 backend/apps/scans/tasks.py 的 planned_scan_steps）。
// hint 對應該階段實際執行的檢查，讓使用者知道現在在分析什麼。
const SCAN_STEP_META = {
  queued: { label: "等待", title: "等待排程", hint: "任務已建立，等待掃描器接手", Icon: StatusQueuedGlyph },
  crawl: { label: "爬取", title: "爬取頁面", hint: "以真實瀏覽器走訪同網域頁面，擷取內容、截圖與行動版版面量測", Icon: StatusCrawlGlyph },
  analyze_seo: { label: "SEO", title: "分析 SEO", hint: "檢查 title、meta description、H1、圖片 alt、canonical 與 Open Graph", Icon: StatusScanGlyph },
  analyze_aeo: { label: "AEO", title: "分析 AEO", hint: "檢查索引與摘要限制，以及結構化資料是否與頁面文字一致", Icon: StatusScanGlyph },
  analyze_geo: { label: "GEO", title: "分析 GEO", hint: "檢查 JSON-LD 實體、可引用段落與 JavaScript 渲染依賴", Icon: StatusScanGlyph },
  analyze_ux: { label: "UX", title: "分析 UX", hint: "檢查行動版破版、觸控目標、表單標籤與 JavaScript 錯誤", Icon: StatusScanGlyph },
  aeo_answers: { label: "問答檢測", title: "AEO 問答檢測", hint: "依網站內容出題，在已掃描頁面中找答案並核對原文證據", Icon: StatusScanGlyph },
  analyze_security: { label: "資安", title: "分析資安", hint: "檢查表單 CSRF，以及頁面中外洩的金鑰與個資", Icon: StatusScanGlyph },
  active_probe: { label: "主動探測", title: "主動探測", hint: "以 Nuclei／Katana 對授權目標執行受控探測", Icon: StatusScanGlyph },
  deep_security: { label: "深度資安", title: "深度資安檢查", hint: "檢查 HTTPS 與安全標頭、TLS 憑證、Cookie、SRI、DNS 與前端套件版本", Icon: StatusScanGlyph },
  exposure_probe: { label: "敏感檔案", title: "敏感檔案探測", hint: "探測常見的敏感檔案路徑是否外洩", Icon: StatusScanGlyph },
  geo_site: { label: "AI 爬蟲", title: "檢查 AI 爬蟲訊號", hint: "檢查 llms.txt 與 robots.txt 對 AI 爬蟲的設定", Icon: StatusScanGlyph },
  agent: { label: "AI Agent", title: "AI Agent 測試", hint: "AI Agent 以擬真使用者操作網站，測試互動流程", Icon: StatusAgentGlyph },
  scoring: { label: "評分", title: "彙整評分", hint: "計算各維度分數並排出優先處理項目", Icon: StatusScanGlyph },
};

const STATUS_FALLBACK_STEP = { crawling: "crawl", scanning: null, agent_testing: "agent" };

/** 由 progress 算出要顯示的階段清單與目前位置；舊任務沒有 steps 時退回四階段。 */
function buildScanSteps(status, progress) {
  const planned = Array.isArray(progress?.steps) ? progress.steps.filter((key) => SCAN_STEP_META[key]) : [];
  if (!planned.length) {
    const idx = Math.max(0, CRAWL_PHASES.findIndex((p) => p.key === status));
    return { detailed: false, steps: CRAWL_PHASES, currentIdx: idx, current: CRAWL_PHASES[idx] };
  }
  const steps = ["queued", ...planned].map((key) => ({ key, ...SCAN_STEP_META[key] }));
  let currentKey = status === "queued" ? "queued" : progress?.step || STATUS_FALLBACK_STEP[status];
  if (!currentKey || !planned.includes(currentKey)) {
    currentKey = status === "scanning" ? planned.find((key) => key.startsWith("analyze_")) || planned[1] : planned[0];
  }
  const currentIdx = Math.max(0, steps.findIndex((step) => step.key === currentKey));
  return { detailed: true, steps, currentIdx, current: steps[currentIdx] };
}

/**
 * 掃描整體進度（掃描詳情的進度條與網站專案總覽共用，確保兩邊數字一致）。
 * 細分階段模式：（已完成階段數＋目前階段完成比例）÷ 階段數；舊任務沿用 pages_done／pages_total。
 */
function scanProgress(status, progress) {
  const built = buildScanSteps(status, progress);
  const { detailed, steps, currentIdx } = built;
  const stepTotal = detailed ? progress?.step_total || 0 : 0;
  const stepDone = detailed ? Math.min(progress?.step_done || 0, stepTotal) : 0;
  const stepFrac = stepTotal > 0 ? stepDone / stepTotal : 0;
  const total = detailed ? steps.length : progress?.pages_total || 0;
  const done = detailed ? currentIdx + stepFrac : progress?.pages_done || 0;
  const hasProgress = total > 0 && (detailed ? status !== "queued" : true);
  const percent = hasProgress ? Math.min(100, Math.round((done / total) * 100)) : null;
  return { ...built, stepTotal, stepDone, stepFrac, total, done, hasProgress, percent };
}

function formatMMSS(totalSec) {
  const sec = Math.max(0, Math.floor(totalSec));
  const mm = String(Math.floor(sec / 60)).padStart(2, "0");
  const ss = String(sec % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

function CrawlingAnimation({
  status,
  hint,
  compact = false,
  progress,
  startedAt,
  onCancel,
  cancelBusy = false,
}) {
  // 每秒重繪，讓「已執行 / 剩餘」會走動
  const [, force] = useState(0);
  useEffect(() => {
    const t = setInterval(() => force((x) => x + 1), 1000);
    return () => clearInterval(t);
  }, []);

  // 整體進度與下方階段列用同一個公式（scanProgress），進度條不會跑在階段前面或後面
  const {
    detailed, steps, currentIdx: safeIdx, current, stepTotal, stepDone, stepFrac, total, done, hasProgress,
    percent: pct,
  } = scanProgress(status, progress);
  const stepUnit = current?.key === "agent" ? "步" : "頁";

  // 已執行時間（從整個 scan 的 started_at 起算）
  const scanStart = startedAt ? new Date(startedAt).getTime() : null;
  const elapsedSec = scanStart ? Math.floor((Date.now() - scanStart) / 1000) : null;

  // ETA：細分模式估「本階段」剩餘（各階段耗時差很多，不拿整體比例外推）；
  // 舊任務沿用 phase 的 elapsed × (total / done - 1)
  let etaSec = null;
  let etaPending = false;
  if (detailed) {
    if (stepTotal > 0 && stepDone > 0 && stepDone < stepTotal && progress?.step_started_at) {
      const stepStart = new Date(progress.step_started_at).getTime();
      const stepElapsed = Math.max(1, Math.floor((Date.now() - stepStart) / 1000));
      etaSec = Math.max(0, Math.round(stepElapsed * (stepTotal / stepDone - 1)));
    }
  } else if (hasProgress && done > 0 && done < total && progress?.phase_started_at) {
    const phaseStart = new Date(progress.phase_started_at).getTime();
    const phaseElapsed = Math.max(1, Math.floor((Date.now() - phaseStart) / 1000));
    etaSec = Math.max(0, Math.round(phaseElapsed * (total / done - 1)));
  } else if (hasProgress && done === 0) {
    // 剛開始掃、還沒抓到第一頁時：avg ≈ 2 秒/頁的粗估，先給使用者一個範圍
    etaPending = true;
  }

  return (
    <div className={`crawl-anim ${compact ? "is-compact" : ""}`}>
      <div className="crawl-anim-header">
        {/* Argus 之眼：掃描進行中的品牌 loader；偏好減少動態者自動換靜態首幀 */}
        <picture className="crawl-anim-eye">
          <source media="(prefers-reduced-motion: reduce)" srcSet={argusEyeStill} />
          <img className="crawl-anim-eye-img" src={argusEye} alt="" width="256" height="202" />
        </picture>
        <div className="crawl-anim-text">
          <div className="crawl-anim-title">{detailed ? current.title : current.label}中...</div>
          {detailed ? <div className="crawl-anim-step-hint">{current.hint}</div> : null}
          {hint ? <div className="crawl-anim-hint">{hint}</div> : null}
        </div>
        <span className="crawl-anim-spinner" aria-hidden="true" />
      </div>

      {(elapsedSec !== null || hasProgress) && (
        <div className="crawl-anim-meta">
          {elapsedSec !== null ? (
            <span className="crawl-meta-chip">
              已執行 <strong>{formatMMSS(elapsedSec)}</strong>
            </span>
          ) : null}
          {hasProgress && detailed ? (
            <>
              <span className="crawl-meta-chip">
                階段 <strong>{safeIdx + 1}/{steps.length}</strong> · 整體 {pct}%
              </span>
              {stepTotal > 0 ? (
                <span className="crawl-meta-chip">
                  {current.label}：<strong>{stepDone}/{stepTotal}</strong> {stepUnit}
                </span>
              ) : null}
            </>
          ) : hasProgress ? (
            <span className="crawl-meta-chip">
              進度 <strong>{done}/{total}</strong> · {pct}%
            </span>
          ) : null}
          {etaSec !== null ? (
            <span className="crawl-meta-chip is-eta">
              {detailed ? "本階段剩餘約" : "剩餘約"} <strong>{formatMMSS(etaSec)}</strong>
            </span>
          ) : etaPending ? (
            <span className="crawl-meta-chip is-eta">
              剩餘時間 <strong>估算中…</strong>
            </span>
          ) : null}
        </div>
      )}

      <div
        className={`crawl-progress ${hasProgress ? "is-determinate" : ""}`}
        role="progressbar"
        aria-label="掃描進度"
        aria-valuenow={pct ?? undefined}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        {hasProgress ? (
          <div className="crawl-progress-fill" style={{ width: `${pct}%` }} />
        ) : (
          <div className="crawl-progress-bar" />
        )}
      </div>

      <ol className={`crawl-phases ${detailed ? "is-detailed" : ""}`} aria-label="掃描階段">
        {steps.map((phase, idx) => {
          let cls = "phase-pending";
          if (idx < safeIdx) cls = "phase-done";
          else if (idx === safeIdx) cls = "phase-active";
          // 每個階段自己的小進度：完成＝滿、進行中＝本階段比例（無法計數時顯示流動條）、未開始＝空
          const segFill = idx < safeIdx ? 1 : idx === safeIdx ? stepFrac : 0;
          const segIndeterminate = idx === safeIdx && stepTotal === 0 && status !== "queued";
          return (
            <li
              key={phase.key}
              className={`crawl-phase ${cls}`}
              title={phase.hint}
              aria-current={idx === safeIdx ? "step" : undefined}
            >
              <span className="crawl-phase-dot" />
              <span className="crawl-phase-emoji" aria-hidden="true">
                {idx < safeIdx ? <StatusDoneGlyph /> : <phase.Icon />}
              </span>
              <span className="crawl-phase-label">{phase.label}</span>
              {detailed ? (
                <span className={`crawl-phase-bar ${segIndeterminate ? "is-indeterminate" : ""}`} aria-hidden="true">
                  <span style={{ width: `${Math.round(segFill * 100)}%` }} />
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>

      {onCancel ? (
        <div className="crawl-anim-actions">
          <button
            type="button"
            className="crawl-cancel-button"
            onClick={onCancel}
            disabled={cancelBusy}
          >
            {cancelBusy ? "終止中..." : "終止掃描"}
          </button>
        </div>
      ) : null}
    </div>
  );
}

// ============================================================
// 建立掃描表單（含 F5 防丟失與草稿持久化）
// ============================================================

function loadScanDraft(key = SCAN_DRAFT_KEY) {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveScanDraft(draft, key = SCAN_DRAFT_KEY) {
  try {
    window.localStorage.setItem(key, JSON.stringify(draft));
  } catch {
    // localStorage 滿了或被禁用時，安靜失敗
  }
}

function clearScanDraft(key = SCAN_DRAFT_KEY) {
  try {
    window.localStorage.removeItem(key);
  } catch {
    // localStorage 被禁用時安靜略過
  }
}

// 網站專案的預設值：起始網址、預設範圍與維度（專案設定頁可改）
function projectFormDefaults(project) {
  return project
    ? {
        url: project.start_url,
        scope: project.default_scope,
        categories: project.default_categories,
        activeMode: project.default_scan_mode === "active",
      }
    : {};
}

// project：網站專案工作區的掃描分頁傳入。網址、範圍、維度以專案預設值起始，草稿按專案分開存
// （A 網站沒送出的設定不會帶到 B 網站）；送出時帶 project，後端拒絕不同網站的網址。
/**
 * @param {{ onCreated: (scan: object) => void, project?: { id: number, name: string, origin: string,
 *   start_url: string, default_scope: string, default_categories: string[] } | null }} props
 */
function ScanJobForm({ onCreated, project = null }) {
  const draftKey = project ? `${SCAN_DRAFT_KEY}:project-${project.id}` : SCAN_DRAFT_KEY;
  const defaults = projectFormDefaults(project);
  // 從 localStorage 還原草稿，避免 F5 後重打網址
  const initial = loadScanDraft(draftKey) || defaults;
  const [scope, setScope] = useState(initial.scope || "site"); // "single" | "site"
  const [url, setUrl] = useState(initial.url || "");
  const [authorizationConfirmed, setAuthorizationConfirmed] = useState(
    initial.authorizationConfirmed || false,
  );
  const [thirdPartyReconfirmed, setThirdPartyReconfirmed] = useState(
    initial.thirdPartyReconfirmed || false,
  );
  const [activeMode, setActiveMode] = useState(initial.activeMode || false);
  const [activeAuthorized, setActiveAuthorized] = useState(initial.activeAuthorized || false);
  // 掃描維度多選（至少一項；費用＝頁數 × 勾選維度數 × 每維單價）
  const [categories, setCategories] = useState(initial.categories || DEFAULT_SCAN_CATEGORIES);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [estimating, setEstimating] = useState(false);
  const [estimate, setEstimate] = useState(null); // { estimated_pages, estimated_cost, confidence }
  const [verifiedDomains, setVerifiedDomains] = useState([]); // 已通過驗證的網域（URL 徽章提示用）
  const navigate = useNavigate();
  const wallet = useArgusStore((s) => s.wallet);
  const fetchWallet = useArgusStore((s) => s.fetchWallet);
  const me = useArgusStore((s) => s.me);
  // 後端 user_owns_domain 對 staff／superuser 一律放行（管理員測試旁路）
  const staffDomainBypass = Boolean(me && (me.is_staff || me.is_superuser));

  // 只抓一次已驗證網域清單（提示用途；失敗時安靜略過，後端仍會擋主動模式）
  useEffect(() => {
    let cancelled = false;
    fetchVerifiedDomains()
      .then((data) => {
        if (!cancelled) setVerifiedDomains(data.results || []);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  // 從目標 URL 抽 hostname（容錯：沒打協定時補 https:// 再試）
  const urlHostname = useMemo(() => {
    const raw = url.trim();
    if (!raw) return "";
    try {
      return new URL(raw).hostname.toLowerCase();
    } catch {
      try {
        return new URL(`https://${raw}`).hostname.toLowerCase();
      } catch {
        return "";
      }
    }
  }, [url]);

  // 命中已有效驗證的網域（含子網域：hostname===domain 或 endswith('.'+domain)）
  const matchedVerifiedDomain = useMemo(() => {
    if (!urlHostname) return null;
    return (
      verifiedDomains.find(
        (item) =>
          item.is_effectively_verified &&
          (urlHostname === item.domain || urlHostname.endsWith(`.${item.domain}`)),
      ) || null
    );
  }, [verifiedDomains, urlHostname]);

  const coinPerCategory = wallet?.coin_per_category ?? 2;
  const coinPerPage = coinPerCategory * categories.length;
  const effectivePages = scope === "single" ? 1 : MAX_SITE_SCAN_PAGES;
  // AI Agent 擬真使用者 UX 測試附加費：僅全網站掃描且勾 UX 時計收（後端 agent 關閉時回 0）。
  const agentUxFee =
    scope !== "single" && categories.includes("ux")
      ? (wallet?.agent_ux_fee ?? 0)
      : 0;
  const estimatedCost = effectivePages * coinPerPage + agentUxFee;
  const balance = wallet?.balance ?? 0;
  const insufficient = balance < estimatedCost;
  const securitySelected = categories.includes("security");

  function toggleCategory(value) {
    const next = categories.includes(value)
      ? categories.filter((item) => item !== value)
      : [...categories, value];
    if (next.length === 0) return; // 至少保留一個維度
    setCategories(next);
    setEstimate(null);
    // 主動測試屬資安維度：取消資安時連動關閉主動模式與其授權勾選
    if (!next.includes("security")) {
      setActiveMode(false);
      setActiveAuthorized(false);
    }
  }

  useEffect(() => {
    saveScanDraft({
      scope,
      url,
      authorizationConfirmed,
      thirdPartyReconfirmed,
      activeMode,
      activeAuthorized,
      categories,
    }, draftKey);
  }, [draftKey, scope, url, authorizationConfirmed, thirdPartyReconfirmed, activeMode, activeAuthorized, categories]);

  useEffect(() => {
    if (!submitting) return undefined;
    const handler = (event) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [submitting]);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      // 單頁掃描：max_pages=1, max_depth=1（不走連結）
      // 整站掃描：遵守專案預設上限，避免過度爬取與預扣過高
      const payload = {
        url,
        authorization_confirmed: authorizationConfirmed,
        third_party_reconfirmed: thirdPartyReconfirmed,
        scan_mode: activeMode ? "active" : "passive",
        active_testing_authorized: activeMode && activeAuthorized,
        categories,
        max_pages: scope === "single" ? 1 : MAX_SITE_SCAN_PAGES,
        max_depth: scope === "single" ? 1 : SITE_SCAN_DEPTH,
        ...(project ? { project: project.id } : {}),
      };
      const response = await api.post("/scans/", payload);
      setUrl(defaults.url || "");
      setAuthorizationConfirmed(false);
      setThirdPartyReconfirmed(false);
      setActiveMode(false);
      setActiveAuthorized(false);
      setCategories(defaults.categories || DEFAULT_SCAN_CATEGORIES);
      setEstimate(null);
      setScope(defaults.scope || "site");
      clearScanDraft(draftKey);
      fetchWallet();
      onCreated(response.data);
      // 保險：直接 navigate 到新掃描的詳情頁。原本依賴 parent ScanLayout 的
      // handleScanCreated 內 navigate，但實機測試發現 setState batch 之後
      // 那個 navigate 偶爾不生效（URL 不變），導致使用者按了「建立掃描」後
      // 還要手動點列表才能進詳情頁。ScanJobForm 自己持有 useNavigate（604 行），
      // 直接呼叫一次最可靠。
      if (response.data?.id) {
        navigate(`/scans/${response.data.id}`);
      }
    } catch (errorResponse) {
      setError(apiErrorMessage(errorResponse, "建立掃描失敗。"));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleEstimate() {
    if (!url || scope === "single") return;
    setEstimating(true);
    setEstimate(null);
    setError("");
    try {
      const res = await api.post("/estimate/", {
        url,
        max_pages: effectivePages,
        categories,
      });
      setEstimate(res.data);
    } catch (err) {
      setError(apiErrorMessage(err, "預估費用失敗，請確認網址格式正確。"));
      setEstimate(null);
    } finally {
      setEstimating(false);
    }
  }

  return (
    <form className="panel space-y-4" onSubmit={handleSubmit}>
      <div>
        <p className="eyebrow">新增任務</p>
        <h2 className="section-title">{project ? `掃描 ${project.name}` : "建立授權掃描"}</h2>
        <p className="mt-1 text-xs text-slate-500">
          {project
            ? `網址需在 ${project.origin} 內；要掃描其他網站，請從上方切換或新增專案。`
            : "表單會自動存草稿；F5 或不小心關閉分頁後再回來，欄位會保留。"}
        </p>
      </div>

      {/* 掃描範圍：兩張卡片擇一 */}
      <div>
        <p className="text-xs font-semibold text-slate-600 mb-2">掃描範圍</p>
        <div className="scope-grid">
          <button
            type="button"
            className={`scope-card ${scope === "single" ? "active" : ""}`}
            aria-pressed={scope === "single"}
            onClick={() => setScope("single")}
          >
            <span className="scope-title">單一頁面</span>
            <span className="scope-desc">只掃描你輸入的這一頁，最快、最省 coin</span>
            <span className="scope-meta">1 頁 = {coinPerPage} coin</span>
          </button>
          <button
            type="button"
            className={`scope-card ${scope === "site" ? "active" : ""}`}
            aria-pressed={scope === "site"}
            onClick={() => setScope("site")}
          >
            <span className="scope-title">整個網站</span>
            <span className="scope-desc">從入口出發爬同網域多頁，產出完整健檢報告</span>
            <span className="scope-meta">最多 {MAX_SITE_SCAN_PAGES} 頁，依實際爬到頁數計費</span>
          </button>
        </div>
      </div>

      {/* 掃描維度：逐項勾選，費用按勾選維度數計算 */}
      <div>
        <p className="text-xs font-semibold text-slate-600 mb-1">
          掃描維度（至少一項）
        </p>
        <p className="text-xs text-slate-500 mb-2">
          費用＝每頁每維度 {coinPerCategory} coin。已選 {categories.length} 維 →
          每頁 {coinPerPage} coin{categories.length === 5 ? "（全選價）" : "，少勾維度即省費用"}。
          {agentUxFee > 0 && <> 全網站掃描含 UX 另加 AI Agent UX 測試 {agentUxFee} coin。</>}
        </p>
        <div className="category-grid">
          {SCAN_CATEGORY_OPTIONS.map(({ value, label, desc }) => {
            const on = categories.includes(value);
            return (
              <button
                type="button"
                key={value}
                className={`scope-card category-card ${on ? "active" : ""}`}
                onClick={() => toggleCategory(value)}
                aria-pressed={on}
              >
                <span className="scope-title">{label}</span>
                <span className="scope-desc">{desc}</span>
                <span className="scope-meta">
                  {on ? `＋${coinPerCategory} coin／頁` : "未選"}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div>
        <label className="text-xs text-slate-500" htmlFor="scan-url">
          {scope === "single" ? "目標頁面網址" : "網站入口網址"}
        </label>
        <input
          id="scan-url"
          className="input"
          placeholder="https://example.com/"
          value={url}
          onChange={(event) => { setUrl(event.target.value); setEstimate(null); }}
        />
        {matchedVerifiedDomain && (
          <div className="scan-verified-badge" role="status">
            <span className="scan-verified-dot" aria-hidden="true" />
            已驗證網域
            {matchedVerifiedDomain.domain !== urlHostname &&
              `（${matchedVerifiedDomain.domain}）`}
            <span className="scan-verified-note">可使用主動式資安測試</span>
          </div>
        )}
        {scope !== "single" && (
          <div className="scan-estimate-row">
            <button
              type="button"
              className="scan-estimate-btn"
              onClick={handleEstimate}
              disabled={estimating || !url}
            >
              {estimating ? "計算中…" : "計算費用上限"}
            </button>
            {estimate && (
              <div
                className="scan-estimate-result"
                role="status"
                aria-live="polite"
              >
                <span>最多 <strong>{estimate.estimated_pages}</strong> 頁，費用上限 <strong>{estimate.estimated_cost}</strong> coin</span>
                <span className="scan-estimate-conf">
                  （依掃描頁數上限計算，完成後退回未使用 coin）
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      <div className={`coin-estimate ${insufficient ? "is-insufficient" : ""}`}>
        <div className="coin-estimate-row">
          <span>本次掃描預扣</span>
          <strong>{estimatedCost.toLocaleString()} coin</strong>
        </div>
        <div className="coin-estimate-row sub">
          <span>目前餘額</span>
          <span>{balance.toLocaleString()} coin</span>
        </div>
        {insufficient && (
          <button
            className="coin-estimate-cta"
            type="button"
            onClick={() => navigate("/billing")}
          >
            點數不足，前往購點 →
          </button>
        )}
        <p className="coin-estimate-hint">
          完成後依實際爬到的頁數退回未使用的 coin；失敗或取消全額退回。
        </p>
      </div>

      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={authorizationConfirmed}
          onChange={(event) => setAuthorizationConfirmed(event.target.checked)}
        />
        我擁有此網站或已獲得書面授權測試。
      </label>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={thirdPartyReconfirmed}
          onChange={(event) => setThirdPartyReconfirmed(event.target.checked)}
        />
        若此網站看似第三方或敏感產業，我已再次確認授權。
      </label>
      <label className={`checkbox-row ${securitySelected ? "" : "opacity-60"}`}>
        <input
          type="checkbox"
          checked={activeMode}
          onChange={(event) => setActiveMode(event.target.checked)}
          disabled={!securitySelected}
        />
        啟用主動式資安測試模式。
        {!securitySelected && "（需先勾選「資安檢測」維度）"}
      </label>
      {activeMode && (
        <label className="checkbox-row warning">
          <input
            type="checkbox"
            checked={activeAuthorized}
            onChange={(event) => setActiveAuthorized(event.target.checked)}
          />
          我同意進行侵入式測試，並理解系統會限制 RPS ≤ 2。
        </label>
      )}
      {activeMode && !matchedVerifiedDomain && !staffDomainBypass && (
        <div className="scan-domain-warning" role="alert">
          <p className="scan-domain-warning-title">⚠ 主動式測試需要先通過網域驗證</p>
          <p className="scan-domain-warning-text">
            {urlHostname
              ? `目標 ${urlHostname} 尚未通過網域所有權驗證，直接送出會被系統拒絕。`
              : "目前輸入的目標尚未通過網域所有權驗證，直接送出會被系統拒絕。"}
            請先完成網域驗證（驗證一次即涵蓋子網域）。
          </p>
          <button
            type="button"
            className="scan-domain-warning-link"
            onClick={() => navigate("/domains")}
          >
            前往網域驗證 →
          </button>
        </div>
      )}
      {activeMode && !matchedVerifiedDomain && staffDomainBypass && (
        <div className="scan-verified-badge" role="status">
          <span className="scan-verified-dot" aria-hidden="true" />
          管理員測試模式：已略過網域驗證閘門
          <span className="scan-verified-note">掃描紀錄仍歸屬您的帳號</span>
        </div>
      )}
      {error && <p className="error-text">{error}</p>}
      <button className="primary-button" type="submit" disabled={submitting}>
        {submitting ? "送出中... (請勿關閉視窗)" : "建立掃描"}
      </button>
    </form>
  );
}

// ============================================================
// 掃描列表
// ============================================================

// 網站專案「掃描」分頁的掃描列表：該網站的全部掃描（卡片多欄、顯示時間與頁數／發現數）。
// 此網站的掃描：一列一次掃描的表格（時間、範圍與模式、頁數、發現、狀態、分數與變化）。
// 不用卡片：同一個網站的歷次掃描本來就是要逐列比較的紀錄。
function ScanList({ scans, onRefresh }) {
  const navigate = useNavigate();
  const inProgressCount = scans.filter((scan) => isInProgress(scan.status)).length;

  // 每次掃描與「前一次有分數的掃描」比較（scans 已按 -created_at 排序，同一專案同一個 origin）
  const deltaById = useMemo(() => {
    const result = new Map();
    const scored = scans.filter((scan) => scan.overall_score !== null && scan.overall_score !== undefined);
    scored.forEach((scan, index) => {
      const previous = scored[index + 1];
      if (previous) result.set(scan.id, scan.overall_score - previous.overall_score);
    });
    return result;
  }, [scans]);

  function openRow(event, scanId) {
    // 列本身可點；列內的連結自己處理
    if (event.target.closest("a, button")) return;
    navigate(`/scans/${scanId}`);
  }

  return (
    <section className="panel scan-list-wide">
      <div className="scan-list-head">
        <div>
          <h2 className="section-title">此網站的掃描</h2>
          <p className="scan-list-sub">
            共 {scans.length} 次
            {inProgressCount > 0 && `，${inProgressCount} 次進行中（每 ${LIST_POLL_INTERVAL_MS / 1000} 秒自動更新）`}
          </p>
        </div>
        <button className="secondary-button" type="button" onClick={onRefresh}>
          重新整理
        </button>
      </div>
      {scans.length ? (
        <div className="scan-ledger-wrap">
          <table className="scan-ledger">
            <thead>
              <tr>
                <th scope="col">建立時間</th>
                <th scope="col">範圍</th>
                <th scope="col" className="is-num">頁數</th>
                <th scope="col" className="is-num">發現</th>
                <th scope="col">狀態</th>
                <th scope="col" className="is-num">分數</th>
              </tr>
            </thead>
            <tbody>
              {scans.map((scan) => {
                const delta = deltaById.get(scan.id);
                const running = isInProgress(scan.status);
                return (
                  <tr
                    key={scan.id}
                    className={running ? "is-running" : ""}
                    onClick={(event) => openRow(event, scan.id)}
                  >
                    <th scope="row">
                      <Link to={`/scans/${scan.id}`} className="scan-ledger-link">
                        {formatDateTime(scan.created_at)}
                      </Link>
                    </th>
                    <td>
                      {scan.max_pages > 1 ? "整個網站" : "單一頁面"}
                      {scan.scan_mode === "active" && <span className="scan-ledger-tag">主動</span>}
                    </td>
                    <td className="is-num">{scan.pages_count ?? "—"}</td>
                    <td className="is-num">{scan.findings_count ?? "—"}</td>
                    <td>
                      <ScanStatusBadge status={scan.status} />
                    </td>
                    <td className="is-num">
                      <ScoreBadge score={scan.overall_score} />
                      {delta !== undefined && delta !== 0 && (
                        <span className={`scan-ledger-delta ${delta > 0 ? "is-up" : "is-down"}`}>
                          {delta > 0 ? `+${delta}` : delta}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="hint-text">這個網站還沒有掃描；用左側表單建立第一次掃描。</p>
      )}
    </section>
  );
}

// ============================================================
// Findings 分組列表（同分類、同標題的 finding 合併為一群組，例如 11 個「頁面未使用 HTTPS」併成一筆，展開後列出每個頁面）
// ============================================================

const SEVERITY_RANK = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };

function buildFindingGroups(findings) {
  const groupMap = new Map();
  for (const finding of findings) {
    const key = `${finding.category}::${finding.title}`;
    let group = groupMap.get(key);
    if (!group) {
      group = {
        key,
        category: finding.category,
        title: finding.title,
        severity: finding.severity,
        description: finding.description,
        remediation: finding.remediation,
        items: [],
      };
      groupMap.set(key, group);
    }
    group.items.push(finding);
    // 群組嚴重度取群內最高
    if (SEVERITY_RANK[finding.severity] < SEVERITY_RANK[group.severity]) {
      group.severity = finding.severity;
    }
  }
  return Array.from(groupMap.values()).sort((a, b) => {
    const sev = SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity];
    if (sev !== 0) return sev;
    if (a.category !== b.category) return a.category.localeCompare(b.category);
    return b.items.length - a.items.length;
  });
}

function FindingsGroupList({
  findings,
  pages,
  scanStatus,
  totalFindings,
  selectedFinding,
  onSelectFinding,
}) {
  const groups = useMemo(() => buildFindingGroups(findings), [findings]);
  const pageMap = useMemo(() => {
    const map = new Map();
    for (const page of pages) {
      map.set(page.id, page);
    }
    return map;
  }, [pages]);

  // 自動展開包含目前 selectedFinding 的群組，並把該群組滾到視野中
  const [expanded, setExpanded] = useState(() => new Set());
  const groupRefs = useRef({});
  useEffect(() => {
    if (!selectedFinding) return;
    const key = `${selectedFinding.category}::${selectedFinding.title}`;
    setExpanded((prev) => {
      if (prev.has(key)) return prev;
      const next = new Set(prev);
      next.add(key);
      return next;
    });
    // 反向跳轉用：當截圖紅框被點時，selectedFinding 變化，把對應建議按鈕滾到視野中央
    const el = groupRefs.current[key];
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [selectedFinding]);

  function toggle(key) {
    const wasExpanded = expanded.has(key);
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
    // 從關閉變展開時，同步選中該群組第一個 finding，
    // 讓使用者點一次群組標題就能同時看到紅色高光框與右側內容，不必再點子項。
    if (!wasExpanded) {
      const group = groups.find((g) => g.key === key);
      if (group && group.items.length > 0) {
        onSelectFinding(group.items[0]);
      }
    }
  }

  if (!groups.length) {
    return (
      <p className="hint-text">
        {totalFindings
          ? "沒有符合篩選條件的項目。"
          : isInProgress(scanStatus)
            ? "尚未發現任何項目，掃描進行中..."
            : "尚無 findings。"}
      </p>
    );
  }

  return (
    <div className="finding-group-list">
      {groups.map((group) => {
        const isExpanded = expanded.has(group.key);
        const containsSelected =
          selectedFinding &&
          selectedFinding.category === group.category &&
          selectedFinding.title === group.title;
        return (
          <div
            key={group.key}
            ref={(el) => {
              if (el) groupRefs.current[group.key] = el;
            }}
            className={`finding-group ${containsSelected ? "active" : ""}`}
          >
            <button
              className="finding-group-header"
              type="button"
              onClick={() => toggle(group.key)}
            >
              <span className={`severity ${group.severity}`}>{SEVERITY_LABEL[group.severity] || group.severity}</span>
              <span className={`category-pill cat-${group.category}`}>
                {CATEGORY_LABELS[group.category] || group.category}
              </span>
              <span className="finding-group-title">{group.title}</span>
              <span className="finding-group-count">{group.items.length}</span>
              <span className="finding-group-chevron" aria-hidden="true">
                {isExpanded ? "▾" : "▸"}
              </span>
            </button>
            {isExpanded && (
              <ul className="finding-group-items">
                {group.items.map((finding) => {
                  const page = finding.page ? pageMap.get(finding.page) : null;
                  const label =
                    page?.url || page?.final_url || "（站台層級）";
                  const isSelected = selectedFinding?.id === finding.id;
                  return (
                    <li key={finding.id}>
                      <button
                        className={`finding-item ${isSelected ? "active" : ""}`}
                        type="button"
                        onClick={() => onSelectFinding(finding)}
                        title={label}
                      >
                        <span className="finding-item-url">{label}</span>
                        {finding.evidence && (
                          <span className="finding-item-evidence">
                            {finding.evidence}
                          </span>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}

function formatEvidenceJson(value) {
  if (!value || (typeof value === "object" && Object.keys(value).length === 0)) {
    return "";
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "";
  }
}

function buildEvidenceCopyText(finding) {
  const lines = [
    `Finding: ${finding.title || ""}`,
    `Category: ${finding.category || ""}`,
    `Severity: ${finding.severity || ""}`,
    `Rule ID: ${finding.rule_id || "N/A"}`,
    ...(finding.owasp_category ? [`OWASP: ${finding.owasp_category}`] : []),
    ...(finding.cwe_id ? [`CWE: ${finding.cwe_id}`] : []),
    `Evidence Source: ${finding.evidence_source || "N/A"}`,
    `Evidence Type: ${finding.evidence_type || "N/A"}`,
    "",
    "Deterministic Evidence:",
    finding.evidence || "N/A",
  ];
  const evidenceJson = formatEvidenceJson(finding.evidence_json);
  if (evidenceJson) {
    lines.push("", "Evidence JSON:", evidenceJson);
  }
  return lines.join("\n");
}

function EvidencePanel({ finding }) {
  const evidenceJson = formatEvidenceJson(finding.evidence_json);
  const hasEvidence =
    finding.evidence ||
    finding.rule_id ||
    finding.evidence_type ||
    finding.evidence_source ||
    evidenceJson;

  if (!hasEvidence) {
    return (
      <div className="evidence-panel is-empty">
        <div className="evidence-panel-header">
          <span className="evidence-panel-title">判定證據</span>
        </div>
        <p>這個發現沒有可追溯的證據。</p>
      </div>
    );
  }

  return (
    <details className="evidence-panel" open>
      <summary className="evidence-panel-header">
        <span className="evidence-panel-title">判定證據</span>
        <span className="evidence-panel-subtitle">由規則引擎產生，可重現</span>
      </summary>

      <div className="evidence-meta-grid">
        <div>
          <span>規則 ID</span>
          <strong>{finding.rule_id || "未標示"}</strong>
        </div>
        <div>
          <span>證據來源</span>
          <strong>{finding.evidence_source || "rule_engine"}</strong>
        </div>
        <div>
          <span>證據型態</span>
          <strong>{finding.evidence_type || "text"}</strong>
        </div>
        {finding.owasp_category && (
          <div>
            <span>OWASP</span>
            <strong>{finding.owasp_category}</strong>
          </div>
        )}
        {finding.cwe_id && (
          <div>
            <span>CWE</span>
            <strong>{finding.cwe_id}</strong>
          </div>
        )}
      </div>

      {finding.evidence && (
        <div className="evidence-block">
          <span className="evidence-block-label">Evidence</span>
          <pre>{finding.evidence}</pre>
        </div>
      )}

      {evidenceJson && (
        <div className="evidence-block">
          <span className="evidence-block-label">Evidence JSON</span>
          <pre>{evidenceJson}</pre>
        </div>
      )}

      {(finding.ai_explanation || finding.ai_remediation || finding.llm_model) && (
        <div className="ai-explanation-block">
          <span className="evidence-block-label">AI 解釋與建議</span>
          {finding.llm_model && <p className="ai-model">模型：{finding.llm_model}</p>}
          {finding.ai_explanation && <p>{finding.ai_explanation}</p>}
          {finding.ai_remediation && <p>{finding.ai_remediation}</p>}
        </div>
      )}

      <button
        className="secondary-button evidence-copy-button"
        type="button"
        onClick={() => navigator.clipboard.writeText(buildEvidenceCopyText(finding))}
      >
        複製 Evidence
      </button>
    </details>
  );
}

// ============================================================
// 截圖畫布（接 selectedFinding 為 prop，以對應 URL 來源）
// ============================================================

function ScreenshotCanvas({ scan, targetPage, findings, selectedFinding, onSelectFinding }) {
  const [imageUrl, setImageUrl] = useState("");
  const [scale, setScale] = useState(1);
  const imageRef = useRef(null);
  // 截圖放在固定高度的捲動視窗裡（整頁截圖動輒上萬像素高，不該把版面撐開）；
  // 選到有位置的發現時，把視窗捲到那個元素
  const viewportRef = useRef(null);

  useEffect(() => {
    let objectUrl = "";
    async function loadScreenshot() {
      // 立即清除舊截圖，避免 revoke 後的失效 URL 讓容器高度歸零，導致 highlight 不可見
      setImageUrl("");
      if (!scan || !targetPage) {
        return;
      }
      try {
        const response = await api.get(
          `/scans/${scan.id}/pages/${targetPage.id}/screenshot/`,
          { responseType: "blob" },
        );
        objectUrl = URL.createObjectURL(response.data);
        setImageUrl(objectUrl);
      } catch {
        // 該頁面尚未產生截圖（爬蟲還沒跑到、或被 robots 擋）靜默失敗
      }
    }
    loadScreenshot();
    return () => {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
    // scan 只認 id：ScanDetailPage 每 2 秒 polling 會產生全新的 scan 物件參考，
    // 若把整個 scan 物件放進依賴陣列，即使內容沒變也會每次重新清空/重抓截圖，畫面閃爍。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scan?.id, targetPage]);

  function syncScale() {
    const image = imageRef.current;
    if (image && image.naturalWidth) {
      setScale(image.clientWidth / image.naturalWidth);
    }
  }

  useEffect(() => {
    window.addEventListener("resize", syncScale);
    return () => window.removeEventListener("resize", syncScale);
  }, []);

  const focusBox =
    selectedFinding?.bounding_box && selectedFinding.page === targetPage?.id
      ? selectedFinding.bounding_box
      : null;
  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport || !imageUrl) return;
    const top = focusBox ? Math.max(0, focusBox.y * scale - 80) : 0;
    viewport.scrollTo?.({ top, behavior: "smooth" });
  }, [focusBox, scale, imageUrl]);

  // 高光框：選中的 finding 在當前頁面且有座標時，畫紅色高光框
  const overlayFindings = findings.filter(
    (finding) => finding.bounding_box && finding.page === targetPage?.id,
  );

  // 站台層級或無 bounding_box 的 finding → 在截圖頂部畫紅色 banner（讓使用者知道「有反應，但不是元素級」）
  const showSiteBanner =
    selectedFinding && !selectedFinding.bounding_box;

  // 確保「按了一定有反應」：沒 bounding_box 時退化為整頁紅色 pulse 外框；
  // 或選的是別頁的 finding（page 對不上 targetPage）也畫整頁外框提示。
  const showWholePageHighlight =
    selectedFinding &&
    (!selectedFinding.bounding_box ||
      (selectedFinding.page && selectedFinding.page !== targetPage?.id));

  return (
    <div className="screenshot-shell">
      {targetPage && (
        <div className="screenshot-caption-row">
          <p className="screenshot-caption" title={targetPage.url}>
            {targetPage.title || targetPage.url}
          </p>
          <a
            className="screenshot-open-link"
            href={targetPage.final_url || targetPage.url}
            target="_blank"
            rel="noopener noreferrer"
            title="在新分頁開啟原網站（可實際互動，但會脫離 Argus 的紅框跳轉）"
          >
            開啟原網頁 ↗
          </a>
        </div>
      )}
      {!imageUrl && (
        isInProgress(scan?.status) ? (
          <div className="screenshot-pending">
            <span className="crawl-anim-spinner" aria-hidden="true" />
            <p className="hint-text">掃描進行中，截圖完成後自動顯示</p>
          </div>
        ) : (
          <p className="hint-text">
            {targetPage
              ? "此頁面沒有可用截圖（可能被 robots.txt 阻擋或回 4xx/5xx）。"
              : "掃描完成並產生截圖後會顯示在此。"}
          </p>
        )
      )}
      {imageUrl && (
        <div className="screenshot-viewport" ref={viewportRef}>
        <div className="relative inline-block">
          <img
            alt="頁面截圖"
            className="screenshot-image"
            ref={imageRef}
            src={imageUrl}
            onLoad={syncScale}
          />
          {showSiteBanner && (
            <div className="site-banner-overlay">
              <span className={`severity ${selectedFinding.severity}`}>
                {SEVERITY_LABEL[selectedFinding.severity] || selectedFinding.severity}
              </span>
              <span className={`category-pill cat-${selectedFinding.category}`}>
                {CATEGORY_LABELS[selectedFinding.category] || selectedFinding.category}
              </span>
              <span className="site-banner-title">
                {selectedFinding.title}（整頁或站台層級，沒有單一元素位置）
              </span>
            </div>
          )}
          {showWholePageHighlight && (
            <div className="whole-page-highlight pointer-events-none" aria-hidden="true" />
          )}
          <div className="pointer-events-none absolute inset-0">
            {overlayFindings.map((finding) => {
              const box = finding.bounding_box;
              const active = selectedFinding?.id === finding.id;
              // 紅框變可點：點下去自動選中對應 finding，達成「截圖 → 建議按鈕」反向跳轉。
              // 外層 div 保留 pointer-events-none 不擋截圖右鍵；個別 highlight-box 在 CSS 中設 pointer-events-auto。
              return (
                <div
                  className={`highlight-box ${active ? "active" : ""}`}
                  key={finding.id}
                  role="button"
                  tabIndex={0}
                  title={`${finding.severity.toUpperCase()} / ${finding.category.toUpperCase()}：${finding.title}（點擊跳到建議）`}
                  onClick={() => onSelectFinding?.(finding)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelectFinding?.(finding);
                    }
                  }}
                  style={{
                    left: `${box.x * scale}px`,
                    top: `${box.y * scale}px`,
                    width: `${box.width * scale}px`,
                    height: `${box.height * scale}px`,
                  }}
                />
              );
            })}
          </div>
        </div>
        </div>
      )}
    </div>
  );
}

// ============================================================
// 互動報告（含進度提示、URL-driven 選擇）
// ============================================================

// DRF 清單端點一次只回一頁（預設 100 筆）。findings 與 pages 在這個畫面上都被
// 當成「全部」使用——截圖疊圖、每頁 finding 計數、頁籤數字、清單本身——只拿
// 第一頁會讓排序靠後的資料整段消失，而且是**靜默**消失：畫面上沒有任何跡象
// 顯示被截斷，看起來就像那些問題不存在。
//
// page_size 直接要到後端上限（ScansPagination.max_page_size = 500），多數掃描
// 一次取完、請求數與過去相同；超過 500 筆才會有第二次往返。
//
// 不使用回應裡的 next 絕對網址：那是 DRF 依請求標頭組出來的，經過反向代理時
// scheme/host 可能與前端實際使用的不一致。自己遞增 page 參數比較可靠。
const LIST_PAGE_SIZE = 500;
const MAX_LIST_PAGES = 20; // 防呆上限：異常巨大的掃描不該把瀏覽器記憶體吃光

async function fetchAllResults(path) {
  const separator = path.includes("?") ? "&" : "?";
  const items = [];
  for (let page = 1; page <= MAX_LIST_PAGES; page += 1) {
    const { data } = await api.get(
      `${path}${separator}page_size=${LIST_PAGE_SIZE}&page=${page}`,
    );
    // 端點若未啟用分頁會直接回陣列，此時第一次就取完了
    if (Array.isArray(data)) return data;
    items.push(...(data.results || []));
    if (!data.next) break;
  }
  return items;
}

function FindingsWorkspace({ scan }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [findings, setFindings] = useState([]);
  const [findingStats, setFindingStats] = useState(null);
  const [pages, setPages] = useState([]);
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [cancelBusy, setCancelBusy] = useState(false);
  const { confirmDialog, notifyDialog, dialogHost } = useConfirmDialogs();

  async function handleCancel() {
    if (!(await confirmDialog("確定要終止此掃描嗎？已收集的部分仍會保留。", { danger: true }))) return;
    setCancelBusy(true);
    try {
      await api.post(`/scans/${scan.id}/cancel/`);
      // 等下次 polling 拿到新 status 切換 UI
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || "未知錯誤";
      notifyDialog("終止失敗：" + detail);
    } finally {
      setCancelBusy(false);
    }
  }

  // findings 與 pages 在 scan 物件更新時跟著刷新（polling 改變 scan 後 findings_count 變動會觸發）
  useEffect(() => {
    let cancelled = false;
    async function loadDetails() {
      try {
        const [allFindings, allPages, statsResponse] = await Promise.all([
          fetchAllResults(`/findings/?scan_id=${scan.id}`),
          fetchAllResults(`/pages/?scan_id=${scan.id}`),
          api.get(`/scans/${scan.id}/finding-stats/`),
        ]);
        if (cancelled) return;
        setFindings(allFindings);
        setPages(allPages);
        setFindingStats(statsResponse.data);
      } catch {
        // polling 會在下一輪重試，這裡不需額外處理
      }
    }
    loadDetails();
    return () => {
      cancelled = true;
    };
  }, [scan.id, scan.findings_count, scan.pages_count, scan.status]);

  // 選中的 finding 由 URL search param 決定，F5 後仍能還原
  const selectedFindingId = searchParams.get("finding");
  const selectedFinding = findings.find((f) => String(f.id) === selectedFindingId) || null;

  // 當前 page tab；URL param `page=<id>` 或 `page=all`；預設 all
  const pageTabParam = searchParams.get("page") || "all";

  function setPageTab(value) {
    const params = new URLSearchParams(searchParams);
    if (value === "all") {
      params.delete("page");
    } else {
      params.set("page", String(value));
    }
    setSearchParams(params, { replace: false });
  }

  function selectFinding(finding) {
    const params = new URLSearchParams(searchParams);
    params.set("finding", String(finding.id));
    // 點 finding 時自動切到對應頁面 tab（站台層級 finding 切到「全站」）
    if (finding.page) {
      params.set("page", String(finding.page));
    } else {
      params.delete("page");
    }
    setSearchParams(params, { replace: false });
  }

  async function downloadReport() {
    const response = await api.get(`/scans/${scan.id}/report/`, {
      responseType: "blob",
    });
    const url = URL.createObjectURL(response.data);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `argus-scan-${scan.id}-report.docx`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  // page tab 過濾：「all」顯示全部、某 page id 顯示該頁與站台級 finding
  const pageFiltered =
    pageTabParam === "all"
      ? findings
      : findings.filter(
          (f) => String(f.page) === pageTabParam || f.page === null,
        );

  const filteredFindings = pageFiltered.filter(
    (finding) =>
      (categoryFilter === "all" || finding.category === categoryFilter) &&
      (severityFilter === "all" || finding.severity === severityFilter),
  );

  // 截圖目標 page：page tab 指定為某 page → 用它；tab=all → 用 selectedFinding 的 page 或 pages[0]
  const targetPage =
    pageTabParam !== "all"
      ? pages.find((p) => String(p.id) === pageTabParam)
      : (selectedFinding?.page &&
          pages.find((p) => p.id === selectedFinding.page)) ||
        pages[0] ||
        null;

  // 計算每個 page 下的 finding 數，給 page tab 顯示徽章
  const findingsPerPage = useMemo(() => {
    const counts = new Map();
    let siteLevel = 0;
    for (const f of findings) {
      if (f.page === null || f.page === undefined) {
        siteLevel += 1;
      } else {
        counts.set(f.page, (counts.get(f.page) || 0) + 1);
      }
    }
    return { perPage: counts, siteLevel };
  }, [findings]);

  // 嚴重度與分類統計一律用後端算好的真實計數。
  //
  // 不能用 findings 陣列自己數：那是 /findings/ 的第一頁（預設 100 筆）。掃描中
  // 總數 < 100 時看起來正常，完成後 findings 一多就只算到第一頁——NTUB 那種 37 頁
  // 的站，前 100 筆幾乎被高 priority 的 SEO 佔滿，AEO 直接從圖上消失，而顯示的
  // 百分比其實是「前 100 筆的佔比」而非全體。
  //
  // 計數尚未載回時退回本地計算，讓圖表在第一次 render 就有東西，不閃空白。
  const severityTotals = useMemo(() => {
    if (findingStats?.by_severity) return findingStats.by_severity;
    const totals = {};
    for (const f of findings) {
      totals[f.severity] = (totals[f.severity] || 0) + 1;
    }
    return totals;
  }, [findingStats, findings]);

  const categoryTotals = useMemo(() => {
    if (findingStats?.by_category) return findingStats.by_category;
    const totals = {};
    for (const f of findings) {
      totals[f.category] = (totals[f.category] || 0) + 1;
    }
    return totals;
  }, [findingStats, findings]);

  const completed = scan.status === "completed";
  const selectedPage = pageTabParam === "all" ? null : pages.find((p) => String(p.id) === pageTabParam) || null;
  const topActions = scan.top_actions || [];

  function pageOptionLabel(page) {
    if (page.depth === 0) return "首頁";
    const path = (page.url || "").replace(scan.origin, "").split("?")[0] || "/";
    const label = page.title?.trim() || path;
    return label.length > 40 ? `${label.slice(0, 40)}…` : label;
  }

  return (
    <>
    <section className="scan-report">
      <header className="panel scan-report-head">
        <div className="scan-report-id">
          <h1 className="scan-report-title">{scan.origin.replace(/^https?:\/\//, "")}</h1>
          <p className="scan-report-meta">
            <ScanStatusBadge status={scan.status} />
            <span>{formatDateTime(scan.completed_at || scan.created_at)}</span>
            <span>{scan.max_pages > 1 ? "整個網站" : "單一頁面"}</span>
            <span>{scan.scan_mode === "active" ? "主動測試" : "被動偵測"}</span>
            <span>{scan.pages_count ?? 0} 頁</span>
            <span>{scan.findings_count ?? 0} 項發現</span>
          </p>
        </div>
        {scan.overall_score !== null && scan.overall_score !== undefined && (
          <p className="scan-report-score">
            <ScoreBadge score={scan.overall_score} />
            <span>網站分數</span>
          </p>
        )}
        <button
          className="secondary-button"
          type="button"
          onClick={downloadReport}
          disabled={!completed}
          title={completed ? "下載這次掃描的 Word 報告" : "掃描完成後可下載"}
        >
          下載 Word 報告
        </button>
      </header>

      {isInProgress(scan.status) && (
        <div className="scan-report-progress">
          <CrawlingAnimation
            status={scan.status}
            progress={scan.progress}
            startedAt={scan.started_at}
            onCancel={handleCancel}
            cancelBusy={cancelBusy}
            hint={`畫面每 ${SCAN_POLL_INTERVAL_MS / 1000} 秒自動更新；可離開此頁，背景會繼續執行`}
          />
          <p className="text-xs text-slate-500">
            為避免無意義的建議，後台路徑（/admin、/wp-admin、/dashboard 等）會跳過 SEO/AEO/GEO
            評分（安全頭部與 CSRF 仍會檢查）；.apk、.zip、.pdf、圖片等下載連結不會列入頁面分析。
          </p>
          {scan.warning_summary && scan.warning_summary.blocked_urls?.length > 0 && (
            <p className="text-xs text-amber-700">
              已偵測到 {scan.warning_summary.blocked_urls.length} 個被阻擋的 URL（403/429/robots.txt）。
            </p>
          )}
        </div>
      )}

      {scan.status === "failed" && (
        <p className="scan-report-alert is-bad">掃描失敗：{scan.error_message || "未知錯誤"}</p>
      )}
      {scan.status === "cancelled" && (
        <p className="scan-report-alert">掃描已終止。已收集到的頁面與發現仍保留在下方。</p>
      )}

      {/* 摘要：嚴重度、各維度、優先處理——放在問題清單與截圖之前，任何寬度都不會被截圖擠到下方 */}
      {(findingStats?.total > 0 || findings.length > 0 || topActions.length > 0) && (
        <div className="scan-summary">
          <section className="panel scan-summary-block">
            <SeverityBarChart severityTotals={severityTotals} title="嚴重度分布" />
          </section>
          <section className="panel scan-summary-block">
            {/* 數的是原始筆數：同一問題出現在多個頁面會分別計入，與下方清單對得上；
                報告裡同名圖數的是合併重複後的項目數 */}
            <h2 className="scan-summary-title">各維度佔比</h2>
            <p className="scan-summary-note">依原始筆數（同一問題在多頁出現會分別計入）</p>
            <StackedBar
              data={Object.keys(CATEGORY_LABELS).map((cat) => ({
                label: CATEGORY_LABELS[cat],
                value: categoryTotals[cat] || 0,
                color: CATEGORY_COLOR[cat],
              }))}
            />
          </section>
          <section className="panel scan-summary-block is-actions">
            <h2 className="scan-summary-title">優先處理</h2>
            {topActions.length ? (
              <ol className="scan-priority-list">
                {topActions.map((action, idx) => (
                  <li key={`${action.category}-${action.title}-${idx}`}>
                    <button
                      className="scan-priority-row"
                      type="button"
                      onClick={() => {
                        // 從現有發現找同分類同標題的第一筆，選中後清單與截圖都會跟著跳過去
                        const matched = findings.find(
                          (f) => f.category === action.category && f.title === action.title,
                        );
                        if (matched) selectFinding(matched);
                      }}
                    >
                      <span className={`severity ${action.severity}`}>
                        {SEVERITY_LABEL[action.severity] || action.severity}
                      </span>
                      <span className="scan-priority-title">{action.title}</span>
                      <span className={`category-pill cat-${action.category}`}>{CATEGORY_LABELS[action.category] || action.category}</span>
                    </button>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="hint-text">
                {isInProgress(scan.status) ? "掃描完成後產生。" : "這次沒有需要優先處理的項目。"}
              </p>
            )}
          </section>
        </div>
      )}

      {/* 檢視器：左邊問題清單、右邊選中問題的說明與頁面截圖 */}
      <div className="scan-inspector">
        <div className="panel scan-inspector-list">
          <div className="scan-inspector-filters">
            <label className="scan-filter">
              <span>頁面</span>
              <select className="input" value={pageTabParam} onChange={(event) => setPageTab(event.target.value)}>
                <option value="all">全站（{findings.length}）</option>
                {pages.map((page) => (
                  <option key={page.id} value={String(page.id)}>
                    {pageOptionLabel(page)}（{findingsPerPage.perPage.get(page.id) || 0}）
                  </option>
                ))}
              </select>
            </label>
            <label className="scan-filter">
              <span>維度</span>
              <select className="input" value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
                {CATEGORY_FILTERS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label className="scan-filter">
              <span>嚴重度</span>
              <select className="input" value={severityFilter} onChange={(event) => setSeverityFilter(event.target.value)}>
                {SEVERITY_FILTERS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
          </div>
          <p className="scan-inspector-count">
            {filteredFindings.length} 項
            {selectedPage ? `（此頁 ${findingsPerPage.perPage.get(selectedPage.id) || 0} 項＋站台層級 ${findingsPerPage.siteLevel} 項）` : ""}
          </p>
          <FindingsGroupList
            findings={filteredFindings}
            pages={pages}
            scanStatus={scan.status}
            totalFindings={findings.length}
            selectedFinding={selectedFinding}
            onSelectFinding={selectFinding}
          />
        </div>

        <div className="panel scan-inspector-preview">
          {selectedFinding ? (
            <article className="finding-detail">
              <p className="finding-detail-meta">
                <span className={`severity ${selectedFinding.severity}`}>
                  {SEVERITY_LABEL[selectedFinding.severity] || selectedFinding.severity}
                </span>
                <span className={`category-pill cat-${selectedFinding.category}`}>{CATEGORY_LABELS[selectedFinding.category] || selectedFinding.category}</span>
              </p>
              <h3 className="finding-detail-title">{selectedFinding.title}</h3>
              <p>{selectedFinding.description}</p>
              <p className="finding-detail-label">怎麼修</p>
              <p>{selectedFinding.remediation}</p>
              <EvidencePanel finding={selectedFinding} />
              <button
                className="secondary-button"
                type="button"
                onClick={() => navigator.clipboard.writeText(selectedFinding.ai_handoff_prompt)}
                title="複製問題、證據與修法，貼給 ChatGPT／Claude 取得更深入的說明"
              >
                複製給 AI 的提示詞
              </button>
            </article>
          ) : (
            <p className="scan-inspector-hint">從左側選一個問題，這裡會顯示說明、修法與證據，截圖會標出位置。</p>
          )}
          <ScreenshotCanvas
            findings={filteredFindings}
            targetPage={targetPage}
            scan={scan}
            selectedFinding={selectedFinding}
            onSelectFinding={selectFinding}
          />
          {/* 複刻是「針對某一頁」的產出，只在選定單一頁面時出現；key 讓切頁時重新掛載，
              避免前一頁還在跑的 polling 把舊結果寫進新頁面的狀態 */}
          {/* 示範專案是虛構網站，複刻連不到目標，不提供 */}
          {scan.is_demo ? null : selectedPage ? (
            <PageRebuildPanel key={selectedPage.id} scan={scan} page={selectedPage} />
          ) : (
            pages.length > 0 && (
              <p className="scan-inspector-hint">
                想複刻並優化某一頁？先在左上「頁面」選擇那一頁。
              </p>
            )
          )}
        </div>
      </div>

      {scan.scan_log?.length > 0 && (
        <details className="scan-log-panel">
          <summary className="scan-log-summary">
            執行紀錄
            <span className="scan-log-count">{scan.scan_log.length} 筆</span>
          </summary>
          <div className="scan-log-body">
            {scan.scan_log.map((entry, i) => (
              <div key={i} className={`scan-log-entry scan-log-${entry.lvl}`}>
                <span className="scan-log-time">
                  {new Date(entry.t).toLocaleTimeString("zh-TW", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                </span>
                <span className="scan-log-lvl">{entry.lvl === "error" ? "ERR" : entry.lvl === "warn" ? "WRN" : "INF"}</span>
                <span className="scan-log-msg">{entry.msg}</span>
              </div>
            ))}
          </div>
        </details>
      )}
    </section>
    {dialogHost}
    </>
  );
}

// ============================================================
// 路由保護與版面
// ============================================================

// 掃描詳情（含拓樸、複刻）的外框：外層 ProjectScanShell 已顯示所屬網站專案的側邊欄，
// 這裡只放返回與「詳情／拓樸」切換。建立掃描與掃描列表在專案的「掃描」分頁。
const SCAN_TABS = [
  { path: "", label: "報告" },
  { path: "topology", label: "網站結構圖" },
  { path: "fixes", label: "修正產出" },
];

function ScanLayout() {
  const { scanId } = useParams();
  const { project } = useOutletContext() || {};
  const backPath = project ? `/projects/${project.id}/scans` : "/projects";

  return (
    <div className="scan-layout detail-mode is-project">
      <div className="scan-content">
        <nav className="scan-subnav" aria-label="這次掃描">
          <Link className="scan-subnav-back" to={backPath}>
            ← {project ? `${project.name} 的所有掃描` : "所有專案"}
          </Link>
          <div className="scan-subnav-tabs">
            {SCAN_TABS.map((tab) => (
              <NavLink
                key={tab.path || "report"}
                to={`/scans/${scanId}${tab.path ? `/${tab.path}` : ""}`}
                end
                className={({ isActive }) => `scan-subnav-tab ${isActive ? "active" : ""}`}
              >
                {tab.label}
              </NavLink>
            ))}
          </div>
        </nav>
        <Outlet context={{ project }} />
      </div>
    </div>
  );
}

/**
 * /scans/:scanId/fixes：修正產出（JSON-LD、OG／meta、llms.txt、FAQ Schema）。
 * 原本放在互動報告最下方；它是要另外產生、另外計點的交付物，獨立成分頁比較清楚。
 */
function ScanFixOutputPage() {
  const { scanId } = useParams();
  const [scan, setScan] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    api
      .get(`/scans/${scanId}/`)
      .then((response) => !cancelled && setScan(response.data))
      .catch(() => !cancelled && setError("無法載入掃描資料，可能不存在或無權限。"));
    return () => {
      cancelled = true;
    };
  }, [scanId]);
  if (error) return <section className="panel"><p className="error-text">{error}</p></section>;
  if (!scan) return <section className="panel"><p className="hint-text">載入中…</p></section>;
  if (scan.status !== "completed") {
    return (
      <section className="panel">
        <p className="hint-text">
          修正產出以完整爬取的內容為事實基礎，掃描完成後才能產生。
        </p>
      </section>
    );
  }
  return <FixOutputSection scan={scan} />;
}

function shortenUrl(url) {
  try {
    const u = new URL(url);
    const tail = (u.pathname + u.search) || "/";
    return tail.length > 28 ? `${tail.slice(0, 25)}...` : tail;
  } catch {
    return url.slice(0, 28);
  }
}

function hostnameOf(url) {
  try {
    return new URL(url).hostname;
  } catch {
    return "";
  }
}

// 從首頁出發做 BFS 樹狀 layout。
// root = depth=0 的節點（爬蟲入口），找不到就用 id 最小者。
// children = 從 outgoing_links 第一次抵達的下游節點（避免迴圈）。
// 每個 subtree 預先算 leaf 數，父節點 y = 子節點群中心，得到對稱不重疊的樹。
// 走不到的孤島塞到樹下方獨立區。
function buildTreeLayout(apiNodes, apiEdges) {
  const COL_W = 280;
  const ROW_H = 96;
  if (apiNodes.length === 0) return { positions: {}, rootId: null, orphanIds: [] };

  const sorted = [...apiNodes].sort(
    (a, b) => (a.depth ?? 99) - (b.depth ?? 99) || a.id - b.id,
  );
  const root = sorted[0];

  const adj = {};
  apiNodes.forEach((n) => { adj[n.id] = []; });
  apiEdges.forEach((e) => {
    if (adj[e.source] && !adj[e.source].includes(e.target)) {
      adj[e.source].push(e.target);
    }
  });

  const parent = { [root.id]: null };
  const visited = new Set([root.id]);
  const queue = [root.id];
  while (queue.length) {
    const cur = queue.shift();
    for (const child of adj[cur] || []) {
      if (!visited.has(child)) {
        visited.add(child);
        parent[child] = cur;
        queue.push(child);
      }
    }
  }

  const children = {};
  apiNodes.forEach((n) => { children[n.id] = []; });
  Object.keys(parent).forEach((id) => {
    const p = parent[Number(id)];
    if (p != null) children[p].push(Number(id));
  });
  Object.values(children).forEach((arr) => arr.sort((a, b) => a - b));

  const leafCount = {};
  function calcLeaves(id) {
    if (!children[id] || children[id].length === 0) {
      leafCount[id] = 1;
      return 1;
    }
    let s = 0;
    for (const c of children[id]) s += calcLeaves(c);
    leafCount[id] = s;
    return s;
  }
  calcLeaves(root.id);

  const positions = {};
  function assign(id, depth, yStart) {
    const span = leafCount[id] * ROW_H;
    positions[id] = { x: depth * COL_W, y: yStart + span / 2 };
    let curY = yStart;
    for (const c of children[id]) {
      const cSpan = leafCount[c] * ROW_H;
      assign(c, depth + 1, curY);
      curY += cSpan;
    }
  }
  assign(root.id, 0, 0);

  const treeMaxY = Math.max(...Object.values(positions).map((p) => p.y), 0);
  const orphans = apiNodes.filter((n) => !visited.has(n.id));
  const ORPHAN_TOP = treeMaxY + 160;
  const ORPHANS_PER_ROW = 4;
  orphans.forEach((n, i) => {
    positions[n.id] = {
      x: (i % ORPHANS_PER_ROW) * COL_W,
      y: ORPHAN_TOP + Math.floor(i / ORPHANS_PER_ROW) * (ROW_H + 24),
    };
  });

  return { positions, rootId: root.id, orphanIds: orphans.map((n) => n.id) };
}

function TopologyCustomNode({ data }) {
  const toneClass = `tone-${data.tone}`;
  let icon = "\u{1F4C4}"; // 📄
  if (data.isRoot) icon = "\u{1F3E0}"; // 🏠
  else if (data.blocked) icon = "\u{26D4}"; // ⛔
  else if (data.isOrphan) icon = "\u{1F4CD}"; // 📍

  let statusText = "無問題";
  if (data.blocked) statusText = "被阻擋";
  else if (data.finding_count > 0) statusText = `${data.finding_count} 個問題`;

  const rootClass = data.isRoot ? "is-root" : "";
  const orphanClass = data.isOrphan ? "is-orphan" : "";

  return (
    <div className={`topology-card ${toneClass} ${rootClass} ${orphanClass}`}>
      <Handle type="target" position={Position.Left} className="topology-handle" />
      <div className="topology-card-icon" aria-hidden="true">{icon}</div>
      <div className="topology-card-body">
        <div className="topology-card-title" title={data.url}>
          {data.isRoot ? "首頁" : data.shortUrl}
        </div>
        <div className="topology-card-host">{data.hostname}</div>
        <div className="topology-card-meta">
          <span className={`topology-status-dot ${toneClass}`} />
          <span>{statusText}</span>
          {data.max_severity && !data.blocked ? (
            <span className="topology-sev-chip">{data.max_severity}</span>
          ) : null}
        </div>
      </div>
      <Handle type="source" position={Position.Right} className="topology-handle" />
    </div>
  );
}

const TOPOLOGY_NODE_TYPES = { topology: TopologyCustomNode };

function TopologyPage() {
  const { scanId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api
      .get(`/scans/${scanId}/topology/`)
      .then((r) => {
        if (!cancelled) setData(r.data);
      })
      .catch(() => {
        if (!cancelled) setLoadError("無法載入拓撲資料，可能掃描尚未完成或無權限。");
      });
    return () => {
      cancelled = true;
    };
  }, [scanId]);

  const { nodes, edges, stats } = useMemo(() => {
    if (!data) return { nodes: [], edges: [], stats: null };

    const { positions, rootId, orphanIds = [] } = buildTreeLayout(data.nodes, data.edges);
    const orphanSet = new Set(orphanIds);

    const rfNodes = data.nodes.map((n) => {
      const pos = positions[n.id] || { x: 0, y: 0 };
      return {
        id: String(n.id),
        type: "topology",
        position: pos,
        data: {
          url: n.url,
          hostname: hostnameOf(n.url),
          shortUrl: shortenUrl(n.url),
          tone: n.tone,
          finding_count: n.finding_count,
          max_severity: n.max_severity,
          blocked: n.blocked,
          isRoot: n.id === rootId,
          isOrphan: orphanSet.has(n.id),
        },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
      };
    });

    const rfEdges = data.edges.map((e, i) => ({
      id: `e${i}-${e.source}-${e.target}`,
      source: String(e.source),
      target: String(e.target),
      type: "smoothstep",
      animated: false,
      markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color: "rgba(56,189,248,0.7)" },
      style: { stroke: "rgba(56, 189, 248, 0.55)", strokeWidth: 1.6 },
    }));

    const summary = {
      total: data.nodes.length,
      with_findings: data.nodes.filter((n) => n.finding_count > 0).length,
      blocked: data.nodes.filter((n) => n.blocked).length,
      orphans: orphanIds.length,
    };

    return { nodes: rfNodes, edges: rfEdges, stats: summary };
  }, [data]);

  function handleNodeClick(_, node) {
    navigate(`/scans/${scanId}?page=${node.id}`);
  }

  if (loadError) {
    return (
      <section className="panel">
        <p className="error-text">{loadError}</p>
      </section>
    );
  }
  if (!data) {
    return (
      <section className="panel">
        <p className="hint-text">載入拓撲資料中...</p>
      </section>
    );
  }
  if (data.nodes.length === 0) {
    return (
      <section className="panel">
        <p className="hint-text">本次掃描沒有可顯示的頁面節點（爬蟲未產生任何 Page）。</p>
      </section>
    );
  }

  return (
    <section className="topology-panel">
      <header className="topology-header">
        <div className="topology-title-row">
          <h2>網站拓撲圖</h2>
          <span className="topology-host-pill">{hostnameOf(data.nodes[0]?.url || "")}</span>
        </div>
        <p className="hint-text">
          以首頁為根節點，沿著實際連結往外分支。節點顏色代表該頁問題嚴重度；點任一節點跳回詳情報告該頁。
        </p>
        {stats ? (
          <div className="topology-stats">
            <span className="topology-stat-chip"><strong>{stats.total}</strong> 頁</span>
            <span className="topology-stat-chip tone-bad"><strong>{stats.with_findings}</strong> 頁有問題</span>
            <span className="topology-stat-chip tone-medium"><strong>{stats.blocked}</strong> 被阻擋</span>
            {stats.orphans > 0 ? (
              <span className="topology-stat-chip"><strong>{stats.orphans}</strong> 孤立頁（無入口連結）</span>
            ) : null}
          </div>
        ) : null}
        <div className="topology-legend">
          <span className="legend-chip tone-good">✓ 無問題</span>
          <span className="legend-chip tone-medium">中度問題</span>
          <span className="legend-chip tone-bad">高/嚴重問題</span>
          <span className="legend-chip">🏠 首頁（根）</span>
          <span className="legend-chip">📍 孤立頁</span>
        </div>
      </header>
      <div className="topology-canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={TOPOLOGY_NODE_TYPES}
          onNodeClick={handleNodeClick}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          nodesDraggable
          nodesConnectable={false}
          minZoom={0.2}
          maxZoom={1.5}
          proOptions={{ hideAttribution: true }}
          defaultEdgeOptions={{ type: "smoothstep" }}
        >
          <Controls showInteractive={false} />
          <MiniMap
            zoomable
            pannable
            nodeColor={(n) => {
              const tone = n.data?.tone;
              if (tone === "bad") return "#fda4af";
              if (tone === "medium") return "#fcd34d";
              return "#86efac";
            }}
            nodeStrokeWidth={2}
            maskColor="rgba(15, 23, 42, 0.08)"
          />
          <Background gap={24} size={1} color="rgba(148, 163, 184, 0.35)" />
        </ReactFlow>
      </div>
    </section>
  );
}

function ScanDetailPage() {
  const { scanId } = useParams();
  const navigate = useNavigate();
  const [scan, setScan] = useState(null);
  const [loadError, setLoadError] = useState("");

  // 首次載入
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const response = await api.get(`/scans/${scanId}/`);
        if (!cancelled) {
          setScan(response.data);
          setLoadError("");
        }
      } catch {
        if (!cancelled) setLoadError("無法載入掃描資料，可能不存在或無權限。");
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [scanId]);

  // 進行中時自動 polling
  const inProgress = scan && isInProgress(scan.status);
  useEffect(() => {
    if (!inProgress) return undefined;
    const timer = setInterval(async () => {
      try {
        const response = await api.get(`/scans/${scanId}/`);
        setScan(response.data);
      } catch {
        // 暫時失敗繼續嘗試
      }
    }, SCAN_POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [inProgress, scanId]);

  if (loadError) {
    return (
      <section className="panel">
        <p className="error-text">{loadError}</p>
        <button
          className="secondary-button mt-3"
          type="button"
          onClick={() => navigate("/projects")}
        >
          回到所有專案
        </button>
      </section>
    );
  }
  if (scan) {
    return <FindingsWorkspace scan={scan} />;
  }
  return (
    <section className="panel">
      <p className="hint-text">載入掃描資料中...</p>
    </section>
  );
}

// ============================================================
// 頂部深色 Navigation（高科技 dashboard 感）
// ============================================================

export {
  scanProgress,
  ScanJobForm,
  ScanLayout,
  ScanList,
  ScanDetailPage,
  ScanFixOutputPage,
  TopologyPage,
  isInProgress,
};
