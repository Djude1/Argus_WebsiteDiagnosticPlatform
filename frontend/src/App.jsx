import { useEffect, useMemo, useRef, useState } from "react";
import { GoogleLogin } from "@react-oauth/google";
import {
  Link,
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
  useLocation,
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

import { api } from "./api";
import { useArgusStore } from "./store";
import introLogo from "./assets/intro-logo.png";
import brandLogo from "./assets/brand-logo.png";

// ============================================================
// 常數
// ============================================================

const CATEGORY_FILTERS = [
  { value: "all", label: "全部分類" },
  { value: "seo", label: "SEO" },
  { value: "aeo", label: "AEO" },
  { value: "geo", label: "GEO" },
  { value: "security", label: "資安" },
  { value: "ux", label: "UX" },
];

const SEVERITY_FILTERS = [
  { value: "all", label: "全部嚴重度" },
  { value: "critical", label: "嚴重" },
  { value: "high", label: "高" },
  { value: "medium", label: "中" },
  { value: "low", label: "低" },
  { value: "info", label: "資訊" },
];

const STATUS_LABELS = {
  queued: { label: "等待中", tone: "slate", emoji: "⏳" },
  crawling: { label: "爬取中", tone: "blue", emoji: "🕷️" },
  scanning: { label: "掃描中", tone: "blue", emoji: "🔍" },
  agent_testing: { label: "Agent 測試中", tone: "blue", emoji: "🤖" },
  completed: { label: "完成", tone: "emerald", emoji: "✓" },
  failed: { label: "失敗", tone: "red", emoji: "✗" },
  cancelled: { label: "已終止", tone: "slate", emoji: "✖" },
};

const IN_PROGRESS_STATUSES = ["queued", "crawling", "scanning", "agent_testing"];

function isInProgress(status) {
  return IN_PROGRESS_STATUSES.includes(status);
}

// ============================================================
// 視覺化元件（純 SVG / CSS，無 chart 套件）
// ============================================================

const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"];
const SEVERITY_COLOR = {
  critical: "#dc2626",
  high: "#f97316",
  medium: "#facc15",
  low: "#38bdf8",
  info: "#94a3b8",
};
const SEVERITY_LABEL = {
  critical: "嚴重",
  high: "高",
  medium: "中",
  low: "低",
  info: "資訊",
};
const CATEGORY_COLOR = {
  security: "#ef4444",
  seo: "#6366f1",
  aeo: "#a855f7",
  geo: "#06b6d4",
  ux: "#10b981",
};

function apiErrorMessage(err, fallback = "操作失敗，請稍後再試。") {
  const data = err?.response?.data;
  if (!data) return fallback;
  if (typeof data === "string") return data;
  if (data.detail) return data.detail;
  const firstKey = Object.keys(data)[0];
  const firstValue = firstKey ? data[firstKey] : null;
  if (Array.isArray(firstValue)) return firstValue.join(" ");
  if (typeof firstValue === "string") return firstValue;
  return fallback;
}

// 數字遞增動畫（適可而止：300ms 線性 ease-out）
function CountUp({ value, duration = 600, suffix = "" }) {
  const [display, setDisplay] = useState(0);
  useEffect(() => {
    const target = Number(value) || 0;
    if (target === 0) {
      setDisplay(0);
      return undefined;
    }
    const start = performance.now();
    let frameId = 0;
    const tick = (now) => {
      const elapsed = now - start;
      const progress = Math.min(1, elapsed / duration);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(target * eased);
      if (progress < 1) {
        frameId = requestAnimationFrame(tick);
      } else {
        setDisplay(target);
      }
    };
    frameId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameId);
  }, [value, duration]);
  const rounded = Number.isInteger(value) ? Math.round(display) : Math.round(display * 10) / 10;
  return (
    <span>
      {rounded}
      {suffix}
    </span>
  );
}

// 水平堆疊比例條：data = [{label, value, color}]，按比例填色
function StackedBar({ data, height = 14 }) {
  const total = data.reduce((sum, item) => sum + (item.value || 0), 0);
  if (total === 0) {
    return <div className="stacked-bar empty" style={{ height }} />;
  }
  return (
    <div className="stacked-bar-wrap">
      <div className="stacked-bar" style={{ height }}>
        {data.map((item) => {
          const pct = (item.value / total) * 100;
          if (pct === 0) return null;
          return (
            <div
              className="stacked-bar-seg"
              key={item.label}
              style={{ width: `${pct}%`, background: item.color }}
              title={`${item.label}: ${item.value} (${pct.toFixed(1)}%)`}
            />
          );
        })}
      </div>
      <div className="stacked-bar-legend">
        {data.map((item) => {
          if (!item.value) return null;
          const pct = (item.value / total) * 100;
          return (
            <div key={item.label} className="stacked-bar-legend-item">
              <span
                className="stacked-bar-swatch"
                style={{ background: item.color }}
                aria-hidden="true"
              />
              <span className="stacked-bar-legend-label">{item.label}</span>
              <span className="stacked-bar-legend-value">{Math.round(pct)}%</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// 嚴重度長條圖（水平、按 SEVERITY_ORDER）
function SeverityBarChart({ severityTotals, title = "Findings 嚴重度分佈" }) {
  const max = Math.max(
    ...SEVERITY_ORDER.map((s) => severityTotals?.[s] || 0),
    1,
  );
  const totalFindings = SEVERITY_ORDER.reduce(
    (sum, s) => sum + (severityTotals?.[s] || 0),
    0,
  );
  return (
    <div className="bar-chart">
      <div className="bar-chart-header">
        <h4>{title}</h4>
        <span className="bar-chart-total">共 {totalFindings}</span>
      </div>
      <div className="bar-chart-rows">
        {SEVERITY_ORDER.map((sev) => {
          const count = severityTotals?.[sev] || 0;
          const pct = (count / max) * 100;
          return (
            <div key={sev} className="bar-chart-row">
              <span className={`bar-chart-label severity ${sev}`}>
                {SEVERITY_LABEL[sev]}
              </span>
              <div className="bar-chart-track">
                <div
                  className="bar-chart-fill"
                  style={{
                    width: `${pct}%`,
                    background: SEVERITY_COLOR[sev],
                    boxShadow: `0 0 8px ${SEVERITY_COLOR[sev]}66`,
                  }}
                />
              </div>
              <span className="bar-chart-count">{count}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// 折線圖：分數趨勢（含座標軸、點標註）
// data = [{label, value}]（按時間舊→新排序）
function LineChart({ data, width = 320, height = 110, ariaLabel }) {
  if (!data || data.length === 0) {
    return <div className="line-chart-empty">無資料</div>;
  }
  const padding = { top: 12, right: 12, bottom: 22, left: 30 };
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;
  const values = data.map((d) => d.value).filter((v) => typeof v === "number");
  if (values.length === 0) {
    return <div className="line-chart-empty">無有效分數</div>;
  }
  const minV = 0;
  const maxV = 100;
  const stepX = data.length > 1 ? plotW / (data.length - 1) : 0;
  const yFor = (v) => padding.top + plotH - ((v - minV) / (maxV - minV)) * plotH;
  const xFor = (i) => padding.left + i * stepX;

  const linePoints = data
    .map((d, i) => (typeof d.value === "number" ? `${xFor(i)},${yFor(d.value)}` : null))
    .filter(Boolean)
    .join(" ");

  const yTicks = [0, 50, 100];
  return (
    <svg
      className="line-chart"
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={ariaLabel || "分數趨勢"}
    >
      {/* Y 軸格線與刻度 */}
      {yTicks.map((tick) => (
        <g key={tick}>
          <line
            x1={padding.left}
            x2={width - padding.right}
            y1={yFor(tick)}
            y2={yFor(tick)}
            className="line-chart-grid"
          />
          <text
            x={padding.left - 6}
            y={yFor(tick) + 3}
            className="line-chart-axis-label"
            textAnchor="end"
          >
            {tick}
          </text>
        </g>
      ))}
      {/* 折線 */}
      <polyline points={linePoints} className="line-chart-line" fill="none" />
      {/* 資料點 */}
      {data.map((d, i) => {
        if (typeof d.value !== "number") return null;
        return (
          <g key={i}>
            <circle
              cx={xFor(i)}
              cy={yFor(d.value)}
              r="3.5"
              className="line-chart-dot"
            />
            <text
              x={xFor(i)}
              y={yFor(d.value) - 7}
              className="line-chart-value"
              textAnchor="middle"
            >
              {d.value}
            </text>
          </g>
        );
      })}
      {/* X 軸標籤：只顯示首末，避免擠 */}
      {data.length > 0 && (
        <>
          <text
            x={xFor(0)}
            y={height - 6}
            className="line-chart-axis-label"
            textAnchor="start"
          >
            {data[0].label}
          </text>
          {data.length > 1 && (
            <text
              x={xFor(data.length - 1)}
              y={height - 6}
              className="line-chart-axis-label"
              textAnchor="end"
            >
              {data[data.length - 1].label}
            </text>
          )}
        </>
      )}
    </svg>
  );
}

// 進行中時的 polling 間隔（毫秒）
const SCAN_POLL_INTERVAL_MS = 2000;
const LIST_POLL_INTERVAL_MS = 3000;
const MAX_SITE_SCAN_PAGES = 50;

// localStorage 暫存表單草稿的 key
const SCAN_DRAFT_KEY = "argus_scan_draft_v1";

// ============================================================
// 通用小元件
// ============================================================

function ScanStatusBadge({ status }) {
  const meta = STATUS_LABELS[status] || { label: status, tone: "slate", emoji: "?" };
  const pulse = isInProgress(status) ? "animate-pulse" : "";
  return (
    <span className={`status-badge status-${meta.tone} ${pulse}`}>
      <span aria-hidden="true">{meta.emoji}</span>
      <span>{meta.label}</span>
    </span>
  );
}

// 四階段進度條：等待 → 爬取 → 掃描 → Agent 測試 → 完成
const CRAWL_PHASES = [
  { key: "queued", label: "等待", emoji: "⏳" },
  { key: "crawling", label: "爬取", emoji: "🕷️" },
  { key: "scanning", label: "掃描", emoji: "🔍" },
  { key: "agent_testing", label: "Agent", emoji: "🤖" },
];

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

  const currentIdx = CRAWL_PHASES.findIndex((p) => p.key === status);
  const safeIdx = currentIdx >= 0 ? currentIdx : 0;
  const current = CRAWL_PHASES[safeIdx] || CRAWL_PHASES[0];

  // progress 結構：{pages_done, pages_total, phase, phase_started_at}
  const total = progress?.pages_total || 0;
  const done = progress?.pages_done || 0;
  const hasProgress = total > 0;
  const pct = hasProgress ? Math.min(100, Math.round((done / total) * 100)) : null;

  // 已執行時間（從整個 scan 的 started_at 起算）
  const scanStart = startedAt ? new Date(startedAt).getTime() : null;
  const elapsedSec = scanStart ? Math.floor((Date.now() - scanStart) / 1000) : null;

  // ETA：基於當前 phase 的 elapsed × (total / done - 1)
  let etaSec = null;
  let etaPending = false;
  if (hasProgress && done > 0 && done < total && progress?.phase_started_at) {
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
        <span className="crawl-anim-spider" aria-hidden="true">{current.emoji}</span>
        <div className="crawl-anim-text">
          <div className="crawl-anim-title">{current.label}中...</div>
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
          {hasProgress ? (
            <span className="crawl-meta-chip">
              進度 <strong>{done}/{total}</strong> · {pct}%
            </span>
          ) : null}
          {etaSec !== null ? (
            <span className="crawl-meta-chip is-eta">
              剩餘約 <strong>{formatMMSS(etaSec)}</strong>
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

      <ol className="crawl-phases">
        {CRAWL_PHASES.map((phase, idx) => {
          let cls = "phase-pending";
          if (idx < safeIdx) cls = "phase-done";
          else if (idx === safeIdx) cls = "phase-active";
          return (
            <li key={phase.key} className={`crawl-phase ${cls}`}>
              <span className="crawl-phase-dot" />
              <span className="crawl-phase-emoji" aria-hidden="true">
                {idx < safeIdx ? "✓" : phase.emoji}
              </span>
              <span className="crawl-phase-label">{phase.label}</span>
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
            {cancelBusy ? "終止中..." : "✖ 終止掃描"}
          </button>
        </div>
      ) : null}
    </div>
  );
}

function ScoreBadge({ score }) {
  if (score === null || score === undefined) {
    return <span className="score-badge muted">尚無分數</span>;
  }
  const tone = score >= 80 ? "good" : score >= 60 ? "medium" : "bad";
  return <span className={`score-badge ${tone}`}>{score}</span>;
}

// ============================================================
// 登入相關
// ============================================================

function NavActions() {
  const { accessToken, setToken, wallet, fetchWallet, me, fetchMe } = useArgusStore();
  const navigate = useNavigate();
  const { canInstall, installed, trigger } = useInstallPrompt();
  // 登入後立刻載入錢包與 me；其他頁面更新（購點、扣 coin）會另外觸發 fetchWallet
  useEffect(() => {
    if (accessToken && !wallet) {
      fetchWallet();
    }
    if (accessToken && !me) {
      fetchMe();
    }
  }, [accessToken, wallet, fetchWallet, me, fetchMe]);
  if (!accessToken) {
    return null;
  }
  function handleLogout() {
    setToken(null);
    navigate("/login");
  }
  const balance = wallet?.balance;
  return (
    <>
      {canInstall && !installed && (
        <button
          className="install-chip"
          type="button"
          onClick={trigger}
          title="把 Argus 安裝到主畫面，像 APP 一樣使用"
        >
          <span aria-hidden="true">⬇</span>
          <span>安裝 APP</span>
        </button>
      )}
      <button
        className="coin-chip"
        type="button"
        onClick={() => navigate("/billing")}
        title="前往購點"
      >
        <span className="coin-chip-icon" aria-hidden="true">💎</span>
        <span className="coin-chip-value">
          {balance == null ? "—" : balance.toLocaleString()}
        </span>
        <span className="coin-chip-unit">coin</span>
      </button>
      <button className="nav-logout-btn" type="button" onClick={handleLogout}>
        登出
      </button>
    </>
  );
}

// ============================================================
// 建立掃描表單（含 F5 防丟失與草稿持久化）
// ============================================================

function loadScanDraft() {
  try {
    const raw = window.localStorage.getItem(SCAN_DRAFT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveScanDraft(draft) {
  try {
    window.localStorage.setItem(SCAN_DRAFT_KEY, JSON.stringify(draft));
  } catch {
    // localStorage 滿了或被禁用時，安靜失敗
  }
}

function clearScanDraft() {
  window.localStorage.removeItem(SCAN_DRAFT_KEY);
}

function ScanJobForm({ onCreated }) {
  // 從 localStorage 還原草稿，避免 F5 後重打網址
  const initial = loadScanDraft() || {};
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
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [estimating, setEstimating] = useState(false);
  const [estimate, setEstimate] = useState(null); // { estimated_pages, estimated_cost, confidence }
  const navigate = useNavigate();
  const wallet = useArgusStore((s) => s.wallet);
  const fetchWallet = useArgusStore((s) => s.fetchWallet);

  const coinPerPage = wallet?.coin_per_page ?? 10;
  const effectivePages = scope === "single" ? 1 : MAX_SITE_SCAN_PAGES;
  const estimatedCost = effectivePages * coinPerPage;
  const balance = wallet?.balance ?? 0;
  const insufficient = balance < estimatedCost;

  useEffect(() => {
    saveScanDraft({
      scope,
      url,
      authorizationConfirmed,
      thirdPartyReconfirmed,
      activeMode,
      activeAuthorized,
    });
  }, [scope, url, authorizationConfirmed, thirdPartyReconfirmed, activeMode, activeAuthorized]);

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
        max_pages: scope === "single" ? 1 : MAX_SITE_SCAN_PAGES,
        max_depth: scope === "single" ? 1 : 3,
      };
      const response = await api.post("/scans/", payload);
      setUrl("");
      setAuthorizationConfirmed(false);
      setThirdPartyReconfirmed(false);
      setActiveMode(false);
      setActiveAuthorized(false);
      setEstimate(null);
      setScope("site");
      clearScanDraft();
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
      const res = await api.post("/estimate/", { url });
      setEstimate(res.data);
    } catch (err) {
      setError(apiErrorMessage(err, "預估費用失敗，請確認網址格式正確、可公開連線。"));
      setEstimate(null);
    } finally {
      setEstimating(false);
    }
  }

  return (
    <form className="panel space-y-4" onSubmit={handleSubmit}>
      <div>
        <p className="eyebrow">新增任務</p>
        <h2 className="section-title">建立授權掃描</h2>
        <p className="mt-1 text-xs text-slate-500">
          表單會自動存草稿；F5 或不小心關閉分頁後再回來，欄位會保留。
        </p>
      </div>

      {/* 掃描範圍：兩張卡片擇一 */}
      <div>
        <p className="text-xs font-semibold text-slate-600 mb-2">掃描範圍</p>
        <div className="scope-grid">
          <button
            type="button"
            className={`scope-card ${scope === "single" ? "active" : ""}`}
            onClick={() => setScope("single")}
          >
            <span className="scope-icon" aria-hidden="true">🎯</span>
            <span className="scope-title">單一頁面</span>
            <span className="scope-desc">只掃描你輸入的這一頁，最快、最省 coin</span>
            <span className="scope-meta">1 頁 = {coinPerPage} coin</span>
          </button>
          <button
            type="button"
            className={`scope-card ${scope === "site" ? "active" : ""}`}
            onClick={() => setScope("site")}
          >
            <span className="scope-icon" aria-hidden="true">🌐</span>
            <span className="scope-title">整個網站</span>
            <span className="scope-desc">從入口出發爬同網域多頁，產出完整健檢報告</span>
            <span className="scope-meta">最多 {MAX_SITE_SCAN_PAGES} 頁，依實際爬到頁數計費</span>
          </button>
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
        {scope !== "single" && (
          <div className="scan-estimate-row">
            <button
              type="button"
              className="scan-estimate-btn"
              onClick={handleEstimate}
              disabled={estimating || !url}
            >
              {estimating ? "估算中…" : "🔍 預估費用"}
            </button>
            {estimate && (
              <div className={`scan-estimate-result conf-${estimate.confidence}`}>
                <span>預估約 <strong>{estimate.estimated_pages}</strong> 頁 ≈ <strong>{estimate.estimated_cost}</strong> coin</span>
                <span className="scan-estimate-conf">
                  {estimate.confidence === "high" ? "（sitemap 精準）" :
                   estimate.confidence === "medium" ? "（連結計算，中等精確）" :
                   "（估算，實際可能不同）"}
                </span>
                {/* 避免使用者看到「10 coin」卻被預扣 500 coin 而誤以為 bug：明示預扣與結算機制 */}
                {Number.isFinite(estimate.estimated_cost) && estimatedCost > estimate.estimated_cost && (
                  <span className="scan-estimate-hold">
                    ⓘ 系統先預扣 <strong>{estimatedCost.toLocaleString()}</strong> coin
                    （上限 {effectivePages} 頁），結束後依實際爬到頁數退回差額。
                  </span>
                )}
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
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={activeMode}
          onChange={(event) => setActiveMode(event.target.checked)}
        />
        啟用主動式資安測試模式。
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

function ScanList({ scans, onRefresh }) {
  const navigate = useNavigate();
  const { scanId } = useParams();
  const activeId = scanId ? Number(scanId) : null;
  const inProgressCount = scans.filter((scan) => isInProgress(scan.status)).length;

  // 每個 origin 上一次的分數，用來算 delta（同 origin 的 scans 已按 -created_at 排序）
  const previousByOrigin = useMemo(() => {
    const seen = new Map();
    const result = new Map();
    for (const scan of scans) {
      if (scan.overall_score === null || scan.overall_score === undefined) continue;
      if (seen.has(scan.origin)) {
        // 第二次見到此 origin，視為「上一次分數」對應第一次見到的那筆
        const firstScanId = seen.get(scan.origin);
        if (!result.has(firstScanId)) {
          result.set(firstScanId, scan.overall_score);
        }
      } else {
        seen.set(scan.origin, scan.id);
      }
    }
    return result;
  }, [scans]);

  return (
    <section className="panel space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <p className="eyebrow">任務</p>
          <h2 className="section-title">掃描列表</h2>
          {inProgressCount > 0 && (
            <p className="mt-1 text-xs text-blue-600">
              🔄 {inProgressCount} 個進行中，畫面每 {LIST_POLL_INTERVAL_MS / 1000} 秒自動更新
            </p>
          )}
          <p className="mt-1 text-[11px] text-slate-500">
            同網址僅顯示最新一次掃描。
            <button
              type="button"
              className="ml-1 underline hover:text-blue-600"
              onClick={() => navigate("/history")}
            >
              查看歷史 →
            </button>
          </p>
        </div>
        <button className="secondary-button" type="button" onClick={onRefresh}>
          重新整理
        </button>
      </div>
      <div className="space-y-2">
        {scans.map((scan) => {
          const tone =
            scan.overall_score === null || scan.overall_score === undefined
              ? "muted"
              : scan.overall_score >= 80
                ? "good"
                : scan.overall_score >= 60
                  ? "medium"
                  : "bad";
          const previous = previousByOrigin.get(scan.id);
          const delta =
            previous !== undefined &&
            scan.overall_score !== null &&
            scan.overall_score !== undefined
              ? scan.overall_score - previous
              : null;
          return (
            <button
              className={`scan-card tone-${tone} ${activeId === scan.id ? "active" : ""} ${
                isInProgress(scan.status) ? "is-in-progress" : ""
              }`}
              key={scan.id}
              type="button"
              onClick={() => navigate(`/scans/${scan.id}`)}
            >
              <span className={`scan-card-stripe tone-${tone}`} aria-hidden="true" />
              {isInProgress(scan.status) && (
                <span className="scan-card-progress-shimmer" aria-hidden="true" />
              )}
              <div className="scan-card-body">
                <p className="scan-card-origin" title={scan.origin}>
                  {scan.origin.replace(/^https?:\/\//, "")}
                </p>
                <div className="scan-card-meta">
                  <ScanStatusBadge status={scan.status} />
                  {delta !== null && delta !== 0 && (
                    <span
                      className={`scan-card-delta tone-${delta > 0 ? "good" : "bad"}`}
                      title="與該網址上一次分數比較"
                    >
                      {delta > 0 ? `▲ +${delta}` : `▼ ${delta}`}
                    </span>
                  )}
                </div>
              </div>
              <ScoreBadge score={scan.overall_score} />
            </button>
          );
        })}
        {!scans.length && <p className="hint-text">尚無掃描任務。</p>}
      </div>
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
    <div className="max-h-[520px] space-y-2 overflow-auto pr-1">
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
              <span className={`severity ${group.severity}`}>{group.severity}</span>
              <span className={`category-pill cat-${group.category}`}>
                {group.category.toUpperCase()}
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
          <span className="evidence-panel-title">Deterministic Evidence</span>
        </div>
        <p>此 Finding 尚未提供可追溯證據。</p>
      </div>
    );
  }

  return (
    <details className="evidence-panel" open>
      <summary className="evidence-panel-header">
        <span className="evidence-panel-title">Deterministic Evidence</span>
        <span className="evidence-panel-subtitle">規則引擎產生，AI 僅負責解釋</span>
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
  }, [scan, targetPage]);

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
          <p className="screenshot-caption">
            📷 {targetPage.title || targetPage.url}
          </p>
          <a
            className="screenshot-open-link"
            href={targetPage.final_url || targetPage.url}
            target="_blank"
            rel="noopener noreferrer"
            title="在新分頁開啟原網站（可實際互動，但會脫離 Argus 的紅框跳轉）"
          >
            🔗 在新分頁開啟原網站
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
                {selectedFinding.severity}
              </span>
              <span className={`category-pill cat-${selectedFinding.category}`}>
                {selectedFinding.category.toUpperCase()}
              </span>
              <span className="site-banner-title">
                ⚠ {selectedFinding.title}
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
      )}
    </div>
  );
}

// ============================================================
// 互動報告（含進度提示、URL-driven 選擇）
// ============================================================

function FindingsWorkspace({ scan }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [findings, setFindings] = useState([]);
  const [pages, setPages] = useState([]);
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [cancelBusy, setCancelBusy] = useState(false);

  async function handleCancel() {
    if (!window.confirm("確定要終止此掃描嗎？已收集的部分仍會保留。")) return;
    setCancelBusy(true);
    try {
      await api.post(`/scans/${scan.id}/cancel/`);
      // 等下次 polling 拿到新 status 切換 UI
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || "未知錯誤";
      alert("終止失敗：" + detail);
    } finally {
      setCancelBusy(false);
    }
  }

  // findings 與 pages 在 scan 物件更新時跟著刷新（polling 改變 scan 後 findings_count 變動會觸發）
  useEffect(() => {
    async function loadDetails() {
      const [findingsResponse, pagesResponse] = await Promise.all([
        api.get(`/findings/?scan_id=${scan.id}`),
        api.get(`/pages/?scan_id=${scan.id}`),
      ]);
      setFindings(findingsResponse.data.results || findingsResponse.data);
      setPages(pagesResponse.data.results || pagesResponse.data);
    }
    loadDetails();
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

  // 嚴重度統計（給長條圖）
  const severityTotals = useMemo(() => {
    const totals = {};
    for (const f of findings) {
      totals[f.severity] = (totals[f.severity] || 0) + 1;
    }
    return totals;
  }, [findings]);

  // 各類別 finding 數（給 Top Actions 堆疊比例條）
  const categoryTotals = useMemo(() => {
    const totals = {};
    for (const f of findings) {
      totals[f.category] = (totals[f.category] || 0) + 1;
    }
    return totals;
  }, [findings]);

  const completed = scan.status === "completed";

  return (
    <section className="panel lg:col-span-2">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <p className="eyebrow">互動報告</p>
          <h2 className="section-title">{scan.origin}</h2>
          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600">
            <ScanStatusBadge status={scan.status} />
            <span>頁面: {scan.pages_count ?? 0}</span>
            <span>Findings: {scan.findings_count ?? 0}</span>
            {scan.overall_score !== null && scan.overall_score !== undefined && (
              <span>分數: {scan.overall_score}</span>
            )}
          </div>
        </div>
        <button
          className="secondary-button"
          type="button"
          onClick={downloadReport}
          disabled={!completed}
        >
          匯出 Word{!completed && "（完成後可用）"}
        </button>
      </div>

      {isInProgress(scan.status) && (
        <div className="mb-4 space-y-2">
          <CrawlingAnimation
            status={scan.status}
            progress={scan.progress}
            startedAt={scan.started_at}
            onCancel={handleCancel}
            cancelBusy={cancelBusy}
            hint={`畫面每 ${SCAN_POLL_INTERVAL_MS / 1000} 秒自動更新；可離開此頁，背景會繼續執行`}
          />
          <p className="text-xs text-slate-500">
            ℹ️ 為避免無意義的建議，後台路徑（/admin、/wp-admin、/dashboard 等）會跳過 SEO/AEO/GEO
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
        <div className="mb-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          ✗ 掃描失敗：{scan.error_message || "未知錯誤"}
        </div>
      )}

      {scan.status === "cancelled" && (
        <div className="mb-4 rounded-xl border border-slate-300 bg-slate-50 p-3 text-sm text-slate-700">
          ✖ 掃描已終止。已收集到的頁面與 finding 仍保留在下方。
        </div>
      )}

      {/* 掃描執行 Log */}
      {scan.scan_log?.length > 0 && (
        <details className="scan-log-panel">
          <summary className="scan-log-summary">
            執行日誌
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

      {/* 頁面 tabs：依不同頁面切換中間截圖區與右側 findings 範圍 */}
      {pages.length > 0 && (
        <div className="page-tabs">
          <button
            type="button"
            className={`page-tab ${pageTabParam === "all" ? "active" : ""}`}
            onClick={() => setPageTab("all")}
          >
            <span className="page-tab-label">全站</span>
            <span className="page-tab-count">{findings.length}</span>
          </button>
          {pages.map((page) => {
            const isHome = page.depth === 0;
            const urlPath = (page.url || "")
              .replace(scan.origin, "")
              .split("?")[0]
              .replace(/^\//, "");
            // 標籤優先用 page.title（更語意化），缺則 fallback 到 URL path
            // 截斷統一 18 字並加 ellipsis，避免「p/412-1000-172.ph」這種被切掉副檔名字尾的歧義
            const rawLabel = (page.title?.trim() || urlPath || `Page ${page.id}`);
            const label = isHome ? "首頁" : (rawLabel.length > 18 ? rawLabel.slice(0, 18) + "…" : rawLabel);
            const cnt = findingsPerPage.perPage.get(page.id) || 0;
            return (
              <button
                key={page.id}
                type="button"
                className={`page-tab ${String(page.id) === pageTabParam ? "active" : ""}`}
                onClick={() => setPageTab(page.id)}
                title={page.url}
              >
                <span className="page-tab-label">{label}</span>
                <span className="page-tab-count">{cnt}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* 整體 viz：嚴重度長條 + 各類別佔比堆疊條 — 完成或進行中皆顯示（進行中是部分資料） */}
      {findings.length > 0 && (
        <div className="report-viz">
          <div className="report-viz-block">
            <SeverityBarChart severityTotals={severityTotals} />
          </div>
          <div className="report-viz-block">
            <h4 className="bar-chart-header-h4">各類別 finding 佔比</h4>
            <StackedBar
              data={Object.keys(CATEGORY_LABELS).map((cat) => ({
                label: CATEGORY_LABELS[cat],
                value: categoryTotals[cat] || 0,
                color: CATEGORY_COLOR[cat],
              }))}
            />
          </div>
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
        <ScreenshotCanvas
          findings={filteredFindings}
          targetPage={targetPage}
          scan={scan}
          selectedFinding={selectedFinding}
          onSelectFinding={selectFinding}
        />
        <div className="space-y-3">
          <div className="top-actions-box">
            <p className="top-actions-title">⚡ Top Actions</p>
            {(scan.top_actions || []).map((action, idx) => (
              <button
                className="top-action-row"
                type="button"
                key={`${action.category}-${action.title}-${idx}`}
                onClick={() => {
                  // 試著從現有 findings 找符合的 finding 自動選中
                  const matched = findings.find(
                    (f) =>
                      f.category === action.category && f.title === action.title,
                  );
                  if (matched) selectFinding(matched);
                }}
              >
                <span className={`severity ${action.severity}`}>{action.severity}</span>
                <span className={`category-pill cat-${action.category}`}>
                  {action.category.toUpperCase()}
                </span>
                <span className="top-action-title">{action.title}</span>
              </button>
            ))}
            {!(scan.top_actions && scan.top_actions.length) && (
              <p className="mt-2 text-sm text-slate-400">
                {isInProgress(scan.status) ? "尚未產生（掃描完成後出現）" : "—"}
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <label className="flex flex-1 flex-col gap-1">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">分類</span>
              <select
                className="input"
                value={categoryFilter}
                onChange={(event) => setCategoryFilter(event.target.value)}
              >
                {CATEGORY_FILTERS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-1 flex-col gap-1">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">嚴重度</span>
              <select
                className="input"
                value={severityFilter}
                onChange={(event) => setSeverityFilter(event.target.value)}
              >
                {SEVERITY_FILTERS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <FindingsGroupList
            findings={filteredFindings}
            pages={pages}
            scanStatus={scan.status}
            totalFindings={findings.length}
            selectedFinding={selectedFinding}
            onSelectFinding={selectFinding}
          />
          {selectedFinding && (
            <div className="finding-detail">
              <h3 className="font-semibold text-slate-900">{selectedFinding.title}</h3>
              <p>{selectedFinding.description}</p>
              <p className="font-semibold">修補方向</p>
              <p>{selectedFinding.remediation}</p>
              <EvidencePanel finding={selectedFinding} />
              <button
                className="primary-button"
                type="button"
                onClick={() => navigator.clipboard.writeText(selectedFinding.ai_handoff_prompt)}
              >
                複製問題 Prompt
              </button>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

// ============================================================
// 路由保護與版面
// ============================================================

function RequireAuth({ children }) {
  const accessToken = useArgusStore((state) => state.accessToken);
  if (accessToken) {
    return children;
  }
  // 使用者直接輸入 /scans/123 之類 deep link 但未登入時，帶 next 讓登入後跳回
  const next = encodeURIComponent(
    window.location.pathname + window.location.search,
  );
  return <Navigate to={`/login?next=${next}`} replace />;
}

// ScanLayout 改為 parent route + Outlet：sidebar（表單 + 列表）只 mount 一次，
// `/scans` ↔ `/scans/:id` 切換只重渲染右側 Outlet，避免每次按「建立掃描」
// 版面整個 unmount 再 remount 造成的跳動。
//
// 兩種模式：
//   list-mode（/scans）：sidebar inline 在左邊，固定 360px。
//   detail-mode（/scans/:id）：sidebar 縮為 drawer overlay，主內容拿到全寬讓截圖變大。
function ScanLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { scanId } = useParams();
  const isDetailPage = Boolean(scanId);
  const isTopologyPage = isDetailPage && location.pathname.endsWith("/topology");
  const [scans, setScans] = useState([]);
  const [drawerOpen, setDrawerOpen] = useState(false);

  async function loadScans() {
    try {
      const response = await api.get("/scans/");
      setScans(response.data.results || response.data);
    } catch {
      // 401 之類靜默失敗，store 變動會自動導回 /login
    }
  }

  useEffect(() => {
    loadScans();
  }, []);

  // 從詳情頁切回列表頁時，自動關閉 drawer 避免 inline sidebar 與 drawer 同時出現
  useEffect(() => {
    if (!isDetailPage) setDrawerOpen(false);
  }, [isDetailPage]);

  // 有任何進行中的 scan 時，自動 polling 列表
  const hasInProgress = scans.some((scan) => isInProgress(scan.status));
  useEffect(() => {
    if (!hasInProgress) return undefined;
    const timer = setInterval(loadScans, LIST_POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [hasInProgress]);

  function handleScanCreated(newScan) {
    loadScans();
    setDrawerOpen(false);
    navigate(`/scans/${newScan.id}`);
  }

  return (
    <div
      className={`scan-layout ${isDetailPage ? "detail-mode" : "list-mode"} ${
        drawerOpen ? "drawer-open" : ""
      }`}
    >
      <aside className="scan-sidebar">
        <ScanJobForm onCreated={handleScanCreated} />
        <ScanList scans={scans} onRefresh={loadScans} />
      </aside>
      {isDetailPage && drawerOpen && (
        <button
          type="button"
          className="scan-sidebar-backdrop"
          aria-label="關閉列表"
          onClick={() => setDrawerOpen(false)}
        />
      )}
      <div className="scan-content">
        {isDetailPage && (
          <div className="scan-content-toolbar">
            <button
              type="button"
              className="drawer-toggle"
              onClick={() => setDrawerOpen((open) => !open)}
              aria-expanded={drawerOpen}
            >
              <span aria-hidden="true">☰</span>
              <span>{drawerOpen ? "收起列表" : "展開列表 / 建立掃描"}</span>
            </button>
            <button
              type="button"
              className="back-to-list-button"
              onClick={() => navigate("/scans")}
            >
              ← 回到掃描列表
            </button>
            {isTopologyPage ? (
              <button
                type="button"
                className="back-to-list-button"
                onClick={() => navigate(`/scans/${scanId}`)}
              >
                📋 回詳情報告
              </button>
            ) : (
              <button
                type="button"
                className="back-to-list-button"
                onClick={() => navigate(`/scans/${scanId}/topology`)}
              >
                🌐 拓撲圖
              </button>
            )}
          </div>
        )}
        <Outlet />
      </div>
    </div>
  );
}

function LoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const accessToken = useArgusStore((s) => s.accessToken);
  const setToken = useArgusStore((s) => s.setToken);
  const [tab, setTab] = useState("google"); // "google" | "login" | "register"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const next = searchParams.get("next");
  const redirect = (!next || next === "/login" || !next.startsWith("/")) ? "/dashboard" : next;

  // 已登入則直接跳轉
  if (accessToken) {
    return <Navigate to={redirect} replace />;
  }

  function handleToken(access) {
    setToken(access);
    navigate(redirect, { replace: true });
  }

  async function handleEmailLogin(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.post("/auth/email-login/", { email, password });
      handleToken(res.data.access);
    } catch (err) {
      setError(err.response?.data?.detail || "登入失敗，請確認 Email 與密碼。");
    } finally {
      setLoading(false);
    }
  }

  async function handleRegister(e) {
    e.preventDefault();
    setError("");
    if (password !== confirmPassword) {
      setError("兩次密碼輸入不一致。");
      return;
    }
    setLoading(true);
    try {
      const res = await api.post("/auth/register/", { email, password });
      handleToken(res.data.access);
    } catch (err) {
      const d = err.response?.data || {};
      setError(d.email || d.password || d.detail || "註冊失敗。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <button
          type="button"
          className="login-back"
          onClick={() => navigate("/project")}
        >
          ← 返回首頁
        </button>
        <div className="login-brand">
          <span className="login-brand-glyph">⟡</span>
          <span className="login-brand-name">ARGUS</span>
        </div>
        <p className="login-sub">授權式 AI 網站健檢平台</p>

        <div className="login-tabs">
          {[
            { key: "google", label: "Google 登入" },
            { key: "login", label: "Email 登入" },
            { key: "register", label: "新帳號" },
          ].map((t) => (
            <button
              key={t.key}
              type="button"
              className={`login-tab ${tab === t.key ? "active" : ""}`}
              onClick={() => { setTab(t.key); setError(""); }}
            >
              {t.label}
            </button>
          ))}
        </div>

        {error && <p className="login-error">{error}</p>}

        {tab === "google" && (
          <div className="login-google-wrap">
            <GoogleLogin
              onSuccess={(credentialResponse) => {
                api.post("/auth/google/", { credential: credentialResponse.credential })
                  .then((res) => handleToken(res.data.access))
                  .catch(() => setError("Google 登入失敗，請稍後再試。"));
              }}
              onError={() => setError("Google 登入元件錯誤，請重新整理。")}
              useOneTap={false}
              theme="filled_black"
              shape="pill"
            />
          </div>
        )}

        {tab === "login" && (
          <form className="login-form" onSubmit={handleEmailLogin}>
            <input
              className="input"
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
            <input
              className="input"
              type="password"
              placeholder="密碼"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
            <button className="login-submit" type="submit" disabled={loading}>
              {loading ? "登入中…" : "登入"}
            </button>
            <p className="login-forgot-hint">
              <button
                type="button"
                className="login-forgot-link"
                onClick={() => navigate("/password-reset")}
              >
                忘記密碼？
              </button>
            </p>
          </form>
        )}

        {tab === "register" && (
          <form className="login-form" onSubmit={handleRegister}>
            <input
              className="input"
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
            <input
              className="input"
              type="password"
              placeholder="密碼（至少 8 字元）"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="new-password"
            />
            <input
              className="input"
              type="password"
              placeholder="確認密碼"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              autoComplete="new-password"
            />
            <button className="login-submit" type="submit" disabled={loading}>
              {loading ? "建立中…" : "建立帳號"}
            </button>
          </form>
        )}

        <p className="login-notice">
          管理員請用上方 Email 登入，登入後於右上角進入 <code>/admin</code> 後台。
        </p>
      </div>
    </div>
  );
}

function PasswordResetRequestPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [serverMessage, setServerMessage] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    try {
      const res = await api.post("/auth/password-reset/request/", {
        email: email.trim().toLowerCase(),
      });
      setServerMessage(res.data?.detail || "若該 Email 已註冊，重設信已寄出。");
      setSubmitted(true);
    } catch {
      // 後端設計為永遠成功；網路錯誤才會走到這
      setServerMessage("送出失敗，請檢查網路連線後再試。");
      setSubmitted(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <button
          type="button"
          className="login-back"
          onClick={() => navigate("/login")}
        >
          ← 返回登入
        </button>
        <div className="login-brand">
          <span className="login-brand-glyph">⟡</span>
          <span className="login-brand-name">重設密碼</span>
        </div>
        <p className="login-sub">輸入註冊時的 Email，我們會寄出重設連結（60 分鐘內有效）。</p>

        {submitted ? (
          <div className="login-info-box">
            <p>{serverMessage}</p>
            <p className="login-info-foot">
              收不到信？請檢查垃圾郵件夾，或確認 Email 是否拼寫正確。
            </p>
            <button
              type="button"
              className="login-submit"
              onClick={() => navigate("/login")}
            >
              回到登入頁
            </button>
          </div>
        ) : (
          <form className="login-form" onSubmit={handleSubmit}>
            <input
              className="input"
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              autoFocus
            />
            <button className="login-submit" type="submit" disabled={loading || !email.trim()}>
              {loading ? "送出中…" : "寄出重設連結"}
            </button>
            <p className="login-forgot-hint">
              Google 帳號的密碼請至 Google 帳號設定管理，本平台無法重設。
            </p>
          </form>
        )}
      </div>
    </div>
  );
}

function PasswordResetConfirmPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = (searchParams.get("token") || "").trim();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("新密碼至少需要 8 個字元。");
      return;
    }
    if (password !== confirm) {
      setError("兩次輸入的密碼不一致。");
      return;
    }
    setLoading(true);
    try {
      await api.post("/auth/password-reset/confirm/", {
        token,
        new_password: password,
      });
      setDone(true);
    } catch (err) {
      const data = err.response?.data || {};
      setError(data.token || data.new_password || data.detail || "重設失敗，請重新申請。");
    } finally {
      setLoading(false);
    }
  }

  if (!token) {
    return (
      <div className="login-page">
        <div className="login-card">
          <button type="button" className="login-back" onClick={() => navigate("/login")}>
            ← 返回登入
          </button>
          <div className="login-brand">
            <span className="login-brand-glyph">⟡</span>
            <span className="login-brand-name">重設密碼</span>
          </div>
          <p className="login-error">
            連結缺少 token；請從信件中重新點擊重設連結，或回到「忘記密碼」重新申請。
          </p>
          <button
            type="button"
            className="login-submit"
            onClick={() => navigate("/password-reset")}
          >
            重新申請
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <button type="button" className="login-back" onClick={() => navigate("/login")}>
          ← 返回登入
        </button>
        <div className="login-brand">
          <span className="login-brand-glyph">⟡</span>
          <span className="login-brand-name">設定新密碼</span>
        </div>

        {done ? (
          <div className="login-info-box">
            <p>密碼已重設成功。</p>
            <p className="login-info-foot">請用新密碼登入。</p>
            <button
              type="button"
              className="login-submit"
              onClick={() => navigate("/login")}
            >
              前往登入
            </button>
          </div>
        ) : (
          <form className="login-form" onSubmit={handleSubmit}>
            <p className="login-sub">請設定新密碼（至少 8 個字元）。設定完成後請用新密碼登入。</p>
            {error && <p className="login-error">{error}</p>}
            <input
              className="input"
              type="password"
              placeholder="新密碼"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="new-password"
              autoFocus
              minLength={8}
            />
            <input
              className="input"
              type="password"
              placeholder="再次輸入新密碼"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              autoComplete="new-password"
              minLength={8}
            />
            <button
              className="login-submit"
              type="submit"
              disabled={loading || !password || !confirm}
            >
              {loading ? "送出中…" : "確認重設"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
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

function ScansPlaceholder() {
  return (
    <section className="panel">
      <p className="hint-text">請從左側選擇一個掃描任務查看互動報告。</p>
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
          onClick={() => navigate("/scans")}
        >
          回到掃描列表
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

const NAV_ITEMS = [
  { to: "/project", label: "首頁", emoji: "🏠" },
  { to: "/dashboard", label: "Dashboard", emoji: "📊" },
  { to: "/scans", label: "掃描", emoji: "🔍" },
  { to: "/history", label: "歷史", emoji: "📈" },
  { to: "/billing", label: "購點", emoji: "💎" },
  { to: "/reviews", label: "評論", emoji: "⭐" },
  { to: "/settings", label: "設定", emoji: "⚙️" },
];

function TopNav() {
  const accessToken = useArgusStore((state) => state.accessToken);
  const replayIntro = useArgusStore((s) => s.replayIntro);
  const location = useLocation();
  if (!accessToken) return null;
  // /admin/* 與公開頁走獨立 layout，不顯示前台 TopNav
  if (location.pathname.startsWith("/admin")) return null;
  if (["/project", "/team", "/purchase", "/download"].some((p) =>
    location.pathname.startsWith(p),
  )) return null;
  // 掃描頁的 top bar 不顯示「評論」入口（首頁等其他頁保留）
  const onScanPage = location.pathname.startsWith("/scans");
  const visibleNavItems = onScanPage
    ? NAV_ITEMS.filter((item) => item.to !== "/reviews")
    : NAV_ITEMS;
  return (
    <nav className="argus-nav">
      <div className="argus-nav-inner">
        <button type="button" className="argus-brand active" onClick={replayIntro} title="重播開場動畫" aria-label="重播 ARGUS 開場動畫">
          <img src={brandLogo} className="argus-brand-logo" alt="ARGUS — AI 網站健檢平台" />
          <span className="argus-brand-sub">AI 網站健檢平台</span>
        </button>
        <div className="argus-nav-links">
          {visibleNavItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `argus-nav-link ${isActive ? "active" : ""}`
              }
            >
              <span aria-hidden="true">{item.emoji}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </div>
        <NavActions />
      </div>
    </nav>
  );
}

// ============================================================
// Dashboard 頁
// ============================================================

const CATEGORY_LABELS = {
  seo: "SEO",
  aeo: "AEO",
  geo: "GEO",
  security: "資安",
  ux: "UX",
};

function ScoreRing({ value, label, size = 96 }) {
  const display = value === null || value === undefined ? "—" : Math.round(value);
  const pct = typeof value === "number" ? Math.max(0, Math.min(100, value)) : 0;
  const tone = pct >= 80 ? "good" : pct >= 60 ? "medium" : "bad";
  const radius = (size - 12) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (pct / 100) * circumference;
  return (
    <div className={`score-ring tone-${tone}`} style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth="8"
          className="ring-track"
          fill="none"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth="8"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          fill="none"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          className="ring-progress"
        />
      </svg>
      <div className="score-ring-text">
        <span className="score-ring-value">{display}</span>
        {label && <span className="score-ring-label">{label}</span>}
      </div>
    </div>
  );
}

function StatTile({ label, value, hint, tone = "neutral", animateValue, onClick }) {
  const inner = (
    <>
      <p className="stat-tile-label">{label}</p>
      <p className="stat-tile-value">
        {typeof animateValue === "number" ? <CountUp value={animateValue} /> : value}
      </p>
      {hint && <p className="stat-tile-hint">{hint}</p>}
    </>
  );
  if (onClick) {
    return (
      <button
        type="button"
        className={`stat-tile tone-${tone} is-clickable`}
        onClick={onClick}
      >
        {inner}
      </button>
    );
  }
  return <div className={`stat-tile tone-${tone}`}>{inner}</div>;
}

// formatRelativeTime 在下方 L3690 已定義，這裡不重複。

// 臨時公告用右下 toast（自動 5 秒消失、不阻斷使用流）；常駐公告用中央 modal（要求使用者確認）。
// 業界做法：把不重要的通知降級為 toast，避免每次小事都打斷使用者操作。
function AnnouncementToast({ announcements, onDismiss }) {
  const [hovering, setHovering] = useState({});

  useEffect(() => {
    // 對每個顯示中的 toast 排 5 秒自動關（hover 時暫停）
    const timers = announcements
      .filter((a) => !hovering[a.id])
      .map((a) =>
        setTimeout(() => onDismiss(a.id), 5000),
      );
    return () => timers.forEach((t) => clearTimeout(t));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [announcements, hovering]);

  if (!announcements.length) return null;
  return (
    <div className="argus-toast-stack" role="status" aria-live="polite">
      {announcements.map((ann) => (
        <div
          key={ann.id}
          className="argus-toast"
          onMouseEnter={() => setHovering((h) => ({ ...h, [ann.id]: true }))}
          onMouseLeave={() => setHovering((h) => ({ ...h, [ann.id]: false }))}
        >
          <div className="argus-toast-body">
            <div className="argus-toast-title">{ann.title}</div>
            <div className="argus-toast-content">{ann.content.slice(0, 100)}{ann.content.length > 100 ? "…" : ""}</div>
          </div>
          <button
            type="button"
            className="argus-toast-close"
            onClick={() => onDismiss(ann.id)}
            aria-label="關閉公告"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}

function AnnouncementModal({ announcements, onDismiss, onConfirm }) {
  const [index, setIndex] = useState(0);
  if (!announcements.length) return null;
  const ann = announcements[index];
  const isLast = index === announcements.length - 1;
  const isPermanent = ann.type === "permanent";

  return (
    <div className="ann-backdrop" role="dialog" aria-modal="true">
      <div className="ann-modal">
        <header className="ann-modal-header">
          <h2 className="ann-modal-title">{ann.title}</h2>
          {!isPermanent && (
            <span className="ann-modal-type-chip">臨時公告</span>
          )}
          {isPermanent && (
            <span className="ann-modal-type-chip permanent">常駐公告</span>
          )}
        </header>
        <div className="ann-modal-body">
          {ann.content.split("\n").map((line, i) => (
            <p key={i} style={{ margin: line ? ".25rem 0" : ".5rem 0" }}>{line || <br />}</p>
          ))}
        </div>
        <footer className="ann-modal-footer">
          {!isPermanent && (
            <button
              className="ann-btn-dismiss"
              onClick={() => onDismiss(ann.id)}
            >
              不再顯示
            </button>
          )}
          {isLast ? (
            <button className="ann-btn-confirm" onClick={() => onConfirm(ann.id)}>
              確認
            </button>
          ) : (
            <button className="ann-btn-confirm" onClick={() => setIndex(index + 1)}>
              下一則 ({index + 1}/{announcements.length})
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}

function DashboardPage() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [categoriesData, setCategoriesData] = useState(null);
  const [error, setError] = useState("");
  const [announcements, setAnnouncements] = useState([]); // permanent → modal
  const [toasts, setToasts] = useState([]); // temporary → toast
  const [annVisible, setAnnVisible] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.get("/dashboard/"), api.get("/findings-by-category/")])
      .then(([dashRes, catRes]) => {
        if (cancelled) return;
        setData(dashRes.data);
        setCategoriesData(catRes.data);
      })
      .catch(() => {
        if (!cancelled) setError("無法載入 Dashboard 資料。");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    api.get("/admin/announcements/active/")
      .then((r) => {
        const all = r.data.announcements || [];
        const toShow = all.filter((ann) => {
          if (ann.type === "temporary") {
            return !localStorage.getItem(`ann_dismissed_${ann.id}`);
          }
          const confirmed = localStorage.getItem(`ann_confirmed_${ann.id}`);
          if (!confirmed) return true;
          return Date.now() - Number(confirmed) > 24 * 60 * 60 * 1000;
        });
        // 分流：temporary → toast (右下、自動消失)；permanent → modal (中央、要求確認)
        const permanent = toShow.filter((a) => a.type === "permanent");
        const temporary = toShow.filter((a) => a.type === "temporary");
        if (permanent.length) {
          setAnnouncements(permanent);
          setAnnVisible(true);
        }
        if (temporary.length) {
          setToasts(temporary);
        }
      })
      .catch(() => {});
  }, []);

  function handleDismiss(annId) {
    localStorage.setItem(`ann_dismissed_${annId}`, "1");
    setToasts((prev) => prev.filter((a) => a.id !== annId));
    const remaining = announcements.filter((a) => a.id !== annId);
    if (!remaining.length) setAnnVisible(false);
    setAnnouncements(remaining);
  }

  function handleConfirm(annId) {
    localStorage.setItem(`ann_confirmed_${annId}`, String(Date.now()));
    setAnnVisible(false);
  }

  if (error) {
    return (
      <section className="panel">
        <p className="error-text">{error}</p>
      </section>
    );
  }
  if (!data) {
    return (
      <section className="panel">
        <p className="hint-text">載入 Dashboard 中...</p>
      </section>
    );
  }

  const { wallet } = data;
  const totalFindings = Object.values(data.severity_totals || {}).reduce(
    (sum, n) => sum + n,
    0,
  );

  return (
    <div className="dashboard-grid">
      <div className="dashboard-hero">
        <div className="dashboard-hero-text">
          <p className="eyebrow text-cyan-300">總覽</p>
          <h2 className="dashboard-hero-title">
            你已執行 <span>{data.total_scans}</span> 次健檢
          </h2>
          <p className="dashboard-hero-sub">
            完成 {data.completed_scans}・失敗 {data.failed_scans}・點數餘額{" "}
            <strong>{wallet?.balance ?? 0}</strong> coin
          </p>
          <div className="dashboard-hero-actions">
            <button
              type="button"
              className="primary-button"
              onClick={() => navigate("/scans")}
            >
              + 開始新掃描
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => navigate("/history")}
            >
              查看歷史
            </button>
          </div>
        </div>
        <ScoreRing value={data.average_score} label="平均分" size={120} />
      </div>

      <div className="stat-grid">
        <StatTile
          label="掃描總數"
          animateValue={data.total_scans}
          hint="所有狀態合計"
          tone="cyan"
        />
        <StatTile
          label="點數餘額"
          animateValue={wallet?.balance || 0}
          hint={`≈ 還能掃 ${Math.floor((wallet?.balance || 0) / (wallet?.coin_per_page || 10)).toLocaleString()} 頁 · 累積花費 NT$ ${(wallet?.total_purchased_ntd || 0).toLocaleString()}`}
          tone="violet"
        />
        <StatTile
          label="累計 Findings"
          animateValue={totalFindings}
          hint="跨所有完成掃描"
          tone="amber"
        />
        <StatTile
          label="高/嚴重"
          animateValue={
            (data.severity_totals?.critical || 0) +
            (data.severity_totals?.high || 0)
          }
          hint="critical + high · 點看清單"
          tone="rose"
          onClick={() => navigate("/scans")}
        />
      </div>

      <div className="panel dashboard-panel">
        <div className="dashboard-panel-header">
          <h3>Findings 嚴重度分佈</h3>
          <span className="hint-text-sm">跨所有掃描</span>
        </div>
        <SeverityBarChart
          severityTotals={data.severity_totals}
          title=""
        />
      </div>

      <div className="panel dashboard-panel">
        <div className="dashboard-panel-header">
          <h3>各類別 finding 佔比</h3>
          <span className="hint-text-sm">哪一類問題最多</span>
        </div>
        <StackedBar
          data={Object.keys(CATEGORY_LABELS).map((cat) => ({
            label: CATEGORY_LABELS[cat],
            value: categoriesData?.categories?.[cat]?.total_findings || 0,
            color: CATEGORY_COLOR[cat],
          }))}
        />
      </div>

      <div className="panel dashboard-panel">
        <div className="dashboard-panel-header">
          <h3>各類別平均</h3>
          <span className="hint-text-sm">基於完成的掃描</span>
        </div>
        <div className="category-rings">
          {Object.keys(CATEGORY_LABELS).map((cat) => (
            <div className="category-ring-item" key={cat}>
              <ScoreRing
                value={data.category_averages?.[cat] ?? null}
                size={84}
              />
              <span className={`category-pill cat-${cat}`}>
                {CATEGORY_LABELS[cat]}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="panel dashboard-panel">
        <div className="dashboard-panel-header">
          <h3>最近掃描</h3>
          <button
            className="secondary-button"
            type="button"
            onClick={() => navigate("/scans")}
          >
            前往掃描頁
          </button>
        </div>
        <ul className="recent-list">
          {data.recent_scans.length === 0 && (
            <li className="text-sm text-slate-400">尚無掃描紀錄。</li>
          )}
          {data.recent_scans.map((scan) => (
            <li key={scan.id}>
              <button
                className="recent-row"
                type="button"
                onClick={() => navigate(`/scans/${scan.id}`)}
              >
                <span className="recent-origin">{scan.origin}</span>
                <span className="recent-time">{formatRelativeTime(scan.completed_at || scan.created_at)}</span>
                <ScanStatusBadge status={scan.status} />
                <ScoreBadge score={scan.overall_score} />
              </button>
            </li>
          ))}
        </ul>
      </div>
      {annVisible && (
        <AnnouncementModal
          announcements={announcements}
          onDismiss={handleDismiss}
          onConfirm={handleConfirm}
        />
      )}
      <AnnouncementToast announcements={toasts} onDismiss={handleDismiss} />
    </div>
  );
}

// ============================================================
// History 頁（同網址歷次分數）
// ============================================================

function Sparkline({ values }) {
  if (!values.length) return <span className="text-slate-400">—</span>;
  const w = 120;
  const h = 32;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = values.length > 1 ? w / (values.length - 1) : 0;
  const points = values
    .map((v, i) => `${i * step},${h - ((v - min) / range) * (h - 6) - 3}`)
    .join(" ");
  return (
    <svg width={w} height={h} className="sparkline">
      <polyline points={points} fill="none" strokeWidth="2" />
    </svg>
  );
}

function HistoryPage() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api
      .get("/history/")
      .then((r) => !cancelled && setData(r.data))
      .catch(() => !cancelled && setError("無法載入歷史資料。"));
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <section className="panel"><p className="error-text">{error}</p></section>;
  if (!data) return <section className="panel"><p className="hint-text">載入中...</p></section>;

  return (
    <section className="panel">
      <div className="dashboard-panel-header">
        <h3>同網址分數歷史</h3>
        <span className="hint-text-sm">每個 origin 的歷次健檢</span>
      </div>
      {data.origins.length === 0 && (
        <p className="mt-3 text-sm text-slate-500">尚無紀錄。</p>
      )}
      <div className="history-grid">
        {data.origins.map((origin) => {
          const chronological = origin.scans
            .filter((s) => s.overall_score !== null && s.overall_score !== undefined)
            .slice()
            .reverse();
          const chartData = chronological.map((s) => ({
            label: new Date(s.created_at).toLocaleDateString("zh-Hant", {
              month: "numeric",
              day: "numeric",
            }),
            value: s.overall_score,
          }));
          const deltaLabel =
            origin.delta === null || origin.delta === undefined
              ? null
              : origin.delta > 0
                ? `▲ +${origin.delta}`
                : origin.delta < 0
                  ? `▼ ${origin.delta}`
                  : "—";
          const deltaTone =
            origin.delta === null || origin.delta === undefined
              ? "neutral"
              : origin.delta >= 0
                ? "good"
                : "bad";
          return (
            <div key={origin.origin} className="history-card">
              <div className="history-card-head">
                <span className="history-origin">{origin.origin}</span>
                <span className="hint-text-sm">{origin.total_scans} 次</span>
              </div>
              <div className="history-card-mid">
                <ScoreBadge score={origin.latest_score} />
                {deltaLabel && (
                  <span className={`history-delta tone-${deltaTone}`}>{deltaLabel}</span>
                )}
              </div>
              {chartData.length > 0 && (
                <div className="history-chart">
                  <LineChart data={chartData} ariaLabel={`${origin.origin} 分數趨勢`} />
                </div>
              )}
              <ul className="history-list">
                {origin.scans.slice(0, 5).map((s, idx) => (
                  <li key={s.id}>
                    <button
                      className={`history-row ${idx === 0 ? "is-latest" : "is-older"}`}
                      type="button"
                      onClick={() => navigate(`/scans/${s.id}`)}
                    >
                      {idx === 0 ? (
                        <span className="history-latest-chip" aria-label="最新">
                          ✨ 最新
                        </span>
                      ) : null}
                      <span className="text-xs text-slate-500">
                        {new Date(s.created_at).toLocaleString("zh-Hant")}
                      </span>
                      <ScanStatusBadge status={s.status} />
                      <ScoreBadge score={s.overall_score} />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// ============================================================
// Billing 頁（4 個方案 + 模擬付款）
// ============================================================

// ----- BillingPage 3 步驟 wizard -----

const WIZARD_STEPS = [
  { id: 1, label: "選擇商品" },
  { id: 2, label: "填寫資料" },
  { id: 3, label: "確認訂購" },
];

function WizardStepper({ current }) {
  return (
    <ol className="wizard-stepper" aria-label="購買流程">
      {WIZARD_STEPS.map((step, idx) => {
        const state = step.id < current ? "done" : step.id === current ? "active" : "pending";
        return (
          <li key={step.id} className={`wizard-step ${state}`}>
            <span className="wizard-step-circle">
              {state === "done" ? "✓" : step.id}
            </span>
            <span className="wizard-step-label">{step.label}</span>
            {idx < WIZARD_STEPS.length - 1 && <span className="wizard-step-bar" />}
          </li>
        );
      })}
    </ol>
  );
}

function BillingPage() {
  const [plans, setPlans] = useState([]);
  const [step, setStep] = useState(1);
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState({});
  const [completedOrder, setCompletedOrder] = useState(null);
  const wallet = useArgusStore((s) => s.wallet);
  const fetchWallet = useArgusStore((s) => s.fetchWallet);
  const me = useArgusStore((s) => s.me);
  const fetchMe = useArgusStore((s) => s.fetchMe);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [buyer, setBuyer] = useState({
    buyer_name: "",
    buyer_email: "",
    invoice_type: "personal",
    company_name: "",
    tax_id: "",
    carrier_type: "cloud",
    carrier_id: "",
    agree_terms: false,
  });

  useEffect(() => {
    api.get("/billing/plans/").then((r) => setPlans(r.data.plans || [])).catch(() => {});
    if (!wallet) fetchWallet();
    if (!me) fetchMe();
  }, [wallet, fetchWallet, me, fetchMe]);

  // 初次拉到 me 時自動填入 email 作為預設
  useEffect(() => {
    if (!me) return;
    setBuyer((prev) => ({
      ...prev,
      buyer_email: prev.buyer_email || me.email || "",
    }));
  }, [me]);

  // 從 /purchase 跳來時帶 ?plan=advanced：plans 載完後自動選好並進 step 2
  useEffect(() => {
    if (selectedPlan || plans.length === 0) return;
    const target = searchParams.get("plan");
    if (!target) return;
    const match = plans.find((p) => p.code === target);
    if (match) {
      setSelectedPlan(match);
      setStep(2);
      // 清掉 URL 上的 plan，避免使用者後續回到 step 1 再選又被自動覆蓋
      setSearchParams({}, { replace: true });
    }
  }, [plans, searchParams, selectedPlan, setSearchParams]);

  function pickPlan(plan) {
    setSelectedPlan(plan);
    setStep(2);
    setErrors({});
  }

  function validateStep2() {
    const errs = {};
    if (!buyer.buyer_name.trim()) errs.buyer_name = "請填寫姓名";
    if (!buyer.buyer_email.trim()) errs.buyer_email = "請填寫 email";
    else if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(buyer.buyer_email)) {
      errs.buyer_email = "email 格式不正確";
    }
    if (buyer.invoice_type === "company") {
      if (!buyer.company_name.trim()) errs.company_name = "公司發票須填公司抬頭";
      if (!/^\d{8}$/.test(buyer.tax_id)) errs.tax_id = "統一編號需為 8 碼數字";
    } else {
      // 個人發票：驗證載具
      if (buyer.carrier_type === "mobile_barcode") {
        if (!/^\/[0-9A-Z+\-.]{7}$/.test(buyer.carrier_id.trim().toUpperCase())) {
          errs.carrier_id = "手機條碼格式錯誤（首碼 / + 7 碼英數，例 /AB12CDE）";
        }
      } else if (buyer.carrier_type === "citizen_digital") {
        if (!/^[A-Z]{2}\d{14}$/.test(buyer.carrier_id.trim().toUpperCase())) {
          errs.carrier_id = "自然人憑證格式錯誤（2 碼英文 + 14 碼數字）";
        }
      }
    }
    if (!buyer.agree_terms) errs.agree_terms = "請勾選同意購買條款";
    return errs;
  }

  function goToConfirm() {
    const errs = validateStep2();
    setErrors(errs);
    if (Object.keys(errs).length === 0) {
      setStep(3);
    }
  }

  async function submitOrder() {
    setSubmitting(true);
    setErrors({});
    try {
      const response = await api.post("/billing/purchase/", {
        plan_code: selectedPlan.code,
        buyer_name: buyer.buyer_name.trim(),
        buyer_email: buyer.buyer_email.trim(),
        invoice_type: buyer.invoice_type,
        company_name: buyer.invoice_type === "company" ? buyer.company_name.trim() : "",
        tax_id: buyer.invoice_type === "company" ? buyer.tax_id.trim() : "",
        carrier_type:
          buyer.invoice_type === "company" ? "cloud" : buyer.carrier_type,
        carrier_id:
          buyer.invoice_type === "company" ? "" :
          (buyer.carrier_type === "cloud" ? "" : buyer.carrier_id.trim().toUpperCase()),
        agree_terms: buyer.agree_terms,
      });
      await fetchWallet();
      setCompletedOrder(response.data.order);
    } catch (err) {
      const data = err?.response?.data || {};
      const flat = {};
      for (const [k, v] of Object.entries(data)) {
        flat[k] = Array.isArray(v) ? v[0] : String(v);
      }
      setErrors(flat);
      if (data.buyer_name || data.buyer_email || data.company_name || data.tax_id || data.agree_terms) {
        setStep(2);
      }
    } finally {
      setSubmitting(false);
    }
  }

  function startNewPurchase() {
    setSelectedPlan(null);
    setStep(1);
    setCompletedOrder(null);
    setErrors({});
    setBuyer((b) => ({ ...b, agree_terms: false }));
  }

  if (completedOrder) {
    return (
      <section className="panel space-y-4">
        <div className="wizard-success">
          <div className="wizard-success-emoji" aria-hidden="true">🎉</div>
          <h2 className="wizard-success-title">訂購完成</h2>
          <p className="wizard-success-sub">已成功購買 {completedOrder.plan_name}</p>
          <dl className="wizard-success-dl">
            <dt>訂單編號</dt><dd>#{completedOrder.id}</dd>
            <dt>方案</dt><dd>{completedOrder.plan_name}</dd>
            <dt>金額</dt><dd>NT$ {completedOrder.price_ntd.toLocaleString()}</dd>
            <dt>入帳點數</dt><dd>+{completedOrder.coin_amount.toLocaleString()} coin</dd>
            <dt>當前餘額</dt><dd className="hl-balance">{wallet?.balance?.toLocaleString()} coin</dd>
            <dt>發票類型</dt><dd>{completedOrder.invoice_type_label}{completedOrder.invoice_type === "company" ? `（${completedOrder.company_name} / ${completedOrder.tax_id}）` : ""}</dd>
            {completedOrder.invoice_type === "personal" && completedOrder.carrier_type !== "cloud" && (
              <>
                <dt>載具</dt>
                <dd>{completedOrder.carrier_type_label}：{completedOrder.carrier_id}</dd>
              </>
            )}
            <dt>收據寄送</dt><dd>{completedOrder.buyer_email}</dd>
          </dl>
          <div className="wizard-success-actions">
            <button className="primary-button" type="button" onClick={startNewPurchase}>
              再買一次
            </button>
            <button className="secondary-button" type="button" onClick={() => navigate("/scans")}>
              開始掃描
            </button>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="panel space-y-4">
      <div>
        <p className="eyebrow">點數商店</p>
        <h2 className="section-title">購買 Argus 點數</h2>
        <p className="mt-1 text-sm text-slate-600">
          每爬一頁需 {wallet?.coin_per_page ?? 10} coin；目前餘額 <strong>{wallet?.balance?.toLocaleString() ?? "—"}</strong> coin。
        </p>
        <div className="billing-test-banner" role="status">
          <span className="billing-test-chip">TEST MODE</span>
          <span>
            目前為<strong>測試環境模擬付款</strong>，不會真的扣款；正式上線將串接金流（Stripe / 綠界 ECPay）。
            點數會立即入帳，並寄送收據到你的 email。
          </span>
        </div>
      </div>

      <WizardStepper current={step} />

      {step === 1 && (
        <div className="billing-plan-grid">
          {plans.map((plan) => {
            const isRecommended = plan.code === "advanced";
            return (
              <div
                key={plan.code}
                className={`billing-plan-card ${isRecommended ? "is-recommended" : ""}`}
              >
                {plan.badge && <span className="billing-plan-badge">{plan.badge}</span>}
                {isRecommended && <span className="billing-plan-recommend">★ 推薦</span>}
                <h3 className="billing-plan-name">{plan.name}</h3>
                <p className="billing-plan-coin">
                  {plan.coin_amount.toLocaleString()} <span>coin</span>
                </p>
                <p className="billing-plan-price">NT$ {plan.price_ntd.toLocaleString()}</p>
                <p className="billing-plan-rate">{plan.coin_per_ntd?.toFixed(2)} coin / NT$</p>
                {plan.description && <p className="billing-plan-desc">{plan.description}</p>}
                <button
                  className="billing-plan-button"
                  type="button"
                  onClick={() => pickPlan(plan)}
                >
                  選擇此方案 →
                </button>
              </div>
            );
          })}
        </div>
      )}

      {step === 2 && selectedPlan && (
        <div className="wizard-form-wrap">
          <div className="wizard-summary-mini">
            <span>已選方案</span>
            <strong>{selectedPlan.name}</strong>
            <span className="wizard-summary-price">
              NT$ {selectedPlan.price_ntd.toLocaleString()} ／ {selectedPlan.coin_amount} coin
            </span>
          </div>

          <div className="wizard-form">
            <div className="wizard-field">
              <label htmlFor="buyer_name">姓名 *</label>
              <input
                id="buyer_name"
                className="input"
                placeholder="王小明"
                value={buyer.buyer_name}
                onChange={(e) => setBuyer({ ...buyer, buyer_name: e.target.value })}
              />
              {errors.buyer_name && <p className="wizard-field-error">{errors.buyer_name}</p>}
            </div>

            <div className="wizard-field">
              <label htmlFor="buyer_email">收據寄送 email *</label>
              <input
                id="buyer_email"
                className="input"
                type="email"
                placeholder="you@example.com"
                value={buyer.buyer_email}
                onChange={(e) => setBuyer({ ...buyer, buyer_email: e.target.value })}
              />
              {errors.buyer_email && <p className="wizard-field-error">{errors.buyer_email}</p>}
            </div>

            {/* 發票設定 */}
            <div className="billing-invoice-section">
              <h4 className="billing-section-title">發票設定</h4>

              {/* 發票類型 */}
              <div className="billing-radio-group">
                <label className="billing-radio-label">
                  <input
                    type="radio"
                    name="invoice_type"
                    checked={buyer.invoice_type === "personal"}
                    onChange={() => setBuyer({ ...buyer, invoice_type: "personal", carrier_type: "cloud", carrier_id: "" })}
                  />
                  個人電子發票
                </label>
                <label className="billing-radio-label">
                  <input
                    type="radio"
                    name="invoice_type"
                    checked={buyer.invoice_type === "company"}
                    onChange={() => setBuyer({ ...buyer, invoice_type: "company", carrier_type: "cloud", carrier_id: "" })}
                  />
                  公司統一發票
                </label>
              </div>

              {/* 個人：載具選擇 */}
              {buyer.invoice_type === "personal" && (
                <div className="billing-carrier-section">
                  <div className="billing-radio-group">
                    <label className="billing-radio-label">
                      <input
                        type="radio"
                        name="carrier_type"
                        checked={buyer.carrier_type === "cloud"}
                        onChange={() => setBuyer({ ...buyer, carrier_type: "cloud", carrier_id: "" })}
                      />
                      雲端發票（自動歸戶，不需載具）
                    </label>
                    <label className="billing-radio-label">
                      <input
                        type="radio"
                        name="carrier_type"
                        checked={buyer.carrier_type === "mobile_barcode"}
                        onChange={() => setBuyer({ ...buyer, carrier_type: "mobile_barcode", carrier_id: "" })}
                      />
                      手機條碼載具
                    </label>
                    <label className="billing-radio-label">
                      <input
                        type="radio"
                        name="carrier_type"
                        checked={buyer.carrier_type === "citizen_digital"}
                        onChange={() => setBuyer({ ...buyer, carrier_type: "citizen_digital", carrier_id: "" })}
                      />
                      自然人憑證載具
                    </label>
                  </div>
                  {buyer.carrier_type !== "cloud" && (
                    <input
                      className={`input ${errors.carrier_id ? "is-error" : ""}`}
                      type="text"
                      placeholder={buyer.carrier_type === "mobile_barcode" ? "/XXXXXXX（手機條碼）" : "AB12345678901234（自然人憑證）"}
                      value={buyer.carrier_id}
                      onChange={(e) => setBuyer({ ...buyer, carrier_id: e.target.value.toUpperCase() })}
                    />
                  )}
                  {errors.carrier_id && <p className="billing-error">{errors.carrier_id}</p>}
                </div>
              )}

              {/* 公司：公司名稱 + 統一編號 */}
              {buyer.invoice_type === "company" && (
                <div className="billing-company-section">
                  <input
                    className={`input ${errors.company_name ? "is-error" : ""}`}
                    type="text"
                    placeholder="公司名稱"
                    value={buyer.company_name || ""}
                    onChange={(e) => setBuyer({ ...buyer, company_name: e.target.value })}
                  />
                  {errors.company_name && <p className="billing-error">{errors.company_name}</p>}
                  <input
                    className={`input ${errors.tax_id ? "is-error" : ""}`}
                    type="text"
                    placeholder="統一編號（8 碼數字）"
                    value={buyer.tax_id || ""}
                    onChange={(e) => setBuyer({ ...buyer, tax_id: e.target.value.replace(/\D/g, "") })}
                    maxLength={8}
                  />
                  {errors.tax_id && <p className="billing-error">{errors.tax_id}</p>}
                </div>
              )}
            </div>

            <div className="wizard-field">
              <label className="wizard-checkbox">
                <input
                  type="checkbox"
                  checked={buyer.agree_terms}
                  onChange={(e) => setBuyer({ ...buyer, agree_terms: e.target.checked })}
                />
                <span>
                  我已閱讀並同意<strong>購買條款</strong>：點數一經入帳不可退費（如需退費請聯絡管理員），
                  並理解本系統為模擬付款。
                </span>
              </label>
              {errors.agree_terms && <p className="wizard-field-error">{errors.agree_terms}</p>}
            </div>
          </div>

          <div className="wizard-nav">
            <button className="secondary-button" type="button" onClick={() => setStep(1)}>
              ← 上一步
            </button>
            <button className="primary-button" type="button" onClick={goToConfirm}>
              下一步：確認訂購 →
            </button>
          </div>
        </div>
      )}

      {step === 3 && selectedPlan && (
        <div className="wizard-confirm">
          <h3 className="wizard-confirm-title">請確認以下訂單資訊</h3>

          <div className="wizard-confirm-card">
            <h4>方案</h4>
            <div className="wizard-confirm-plan">
              <div>
                <div className="wizard-confirm-plan-name">{selectedPlan.name}</div>
                <div className="wizard-confirm-plan-coin">{selectedPlan.coin_amount.toLocaleString()} coin</div>
              </div>
              <div className="wizard-confirm-plan-price">NT$ {selectedPlan.price_ntd.toLocaleString()}</div>
            </div>
          </div>

          <div className="wizard-confirm-card">
            <h4>買家資訊</h4>
            <dl className="wizard-confirm-dl">
              <dt>姓名</dt><dd>{buyer.buyer_name}</dd>
              <dt>email</dt><dd>{buyer.buyer_email}</dd>
              <dt>發票</dt>
              <dd>
                {buyer.invoice_type === "company"
                  ? `公司發票（${buyer.company_name} / 統編 ${buyer.tax_id}）`
                  : "個人電子發票"}
              </dd>
              {buyer.invoice_type === "personal" && (
                <>
                  <dt>載具</dt>
                  <dd>
                    {buyer.carrier_type === "cloud" && "雲端發票（寄 email）"}
                    {buyer.carrier_type === "mobile_barcode" && `手機條碼 ${buyer.carrier_id}`}
                    {buyer.carrier_type === "citizen_digital" && `自然人憑證 ${buyer.carrier_id}`}
                  </dd>
                </>
              )}
            </dl>
          </div>

          <div className="wizard-confirm-total">
            <span>應付金額</span>
            <span className="wizard-confirm-total-value">NT$ {selectedPlan.price_ntd.toLocaleString()}</span>
          </div>
          {(() => {
            // 以最便宜方案（sort_order 最小）的單位單價為基準，算「比 N 次最便宜方案省多少」
            const baseline = [...plans].sort((a, b) => a.price_ntd - b.price_ntd)[0];
            if (!baseline || baseline.code === selectedPlan.code) return null;
            const baselineRate = baseline.coin_amount / baseline.price_ntd;
            const fairPrice = Math.round(selectedPlan.coin_amount / baselineRate);
            const saved = fairPrice - selectedPlan.price_ntd;
            if (saved <= 0) return null;
            const pct = Math.round((saved / fairPrice) * 100);
            return (
              <p className="wizard-confirm-saved">
                相比同等 coin 數量買{baseline.name}，這個方案省下 NT$ {saved.toLocaleString()}（約 {pct}%）。
              </p>
            );
          })()}

          {Object.keys(errors).length > 0 && (
            <div className="billing-feedback tone-bad">
              {Object.values(errors).join("、")}
            </div>
          )}

          <div className="wizard-nav">
            <button className="secondary-button" type="button" onClick={() => setStep(2)} disabled={submitting}>
              ← 修改資料
            </button>
            <button className="primary-button" type="button" onClick={submitOrder} disabled={submitting}>
              {submitting ? "處理中…" : "確認購買（模擬付款）"}
            </button>
          </div>
        </div>
      )}

    </section>
  );
}

// ============================================================
// Reviews 頁（Trustpilot 風格：所有人看得到，自己可寫/改）
// ============================================================

function StarRating({ value, onChange, readOnly = false, size = 24 }) {
  const stars = [1, 2, 3, 4, 5];
  return (
    <div className={`star-rating ${readOnly ? "is-read" : ""}`} role="radiogroup">
      {stars.map((n) => (
        <button
          key={n}
          type="button"
          className={`star ${n <= (value || 0) ? "filled" : ""}`}
          style={{ fontSize: size }}
          onClick={readOnly ? undefined : () => onChange?.(n)}
          aria-label={`${n} 星`}
          disabled={readOnly}
        >
          ★
        </button>
      ))}
    </div>
  );
}

// 相對時間 helper：3 分鐘前 / 2 小時前 / 1 天前 / 1 個月前
function formatRelativeTime(isoString) {
  if (!isoString) return "";
  const now = Date.now();
  const then = new Date(isoString).getTime();
  const sec = Math.floor((now - then) / 1000);
  if (sec < 60) return "剛剛";
  if (sec < 3600) return `${Math.floor(sec / 60)} 分鐘前`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} 小時前`;
  const days = Math.floor(sec / 86400);
  if (days < 30) return `${days} 天前`;
  if (days < 365) return `${Math.floor(days / 30)} 個月前`;
  return `${Math.floor(days / 365)} 年前`;
}

// 取出第一個字當 avatar 縮寫
function getAvatarLetter(name) {
  if (!name) return "?";
  const trimmed = name.trim();
  return trimmed.charAt(0).toUpperCase();
}

// 從名字算 hash 取 6 種顏色之一（avatar 背景色）
function avatarColorFor(name) {
  const colors = [
    "#06b6d4", "#6366f1", "#ec4899", "#f59e0b", "#10b981", "#a855f7",
  ];
  let h = 0;
  for (let i = 0; i < (name || "").length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return colors[h % colors.length];
}

// 圖片 lightbox modal
function ImageLightbox({ url, onClose }) {
  useEffect(() => {
    function onKey(e) { if (e.key === "Escape") onClose(); }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  if (!url) return null;
  return (
    <div className="lightbox-backdrop" onClick={onClose}>
      <button type="button" className="lightbox-close" onClick={onClose} aria-label="關閉">×</button>
      <img src={url} alt="預覽" className="lightbox-image" onClick={(e) => e.stopPropagation()} />
    </div>
  );
}

function ReviewMessageBubble({ msg, onHelpful, onImageClick }) {
  const sideClass = msg.is_admin ? "is-admin" : "is-user";
  const avatar = msg.is_admin ? "🛡️" : getAvatarLetter(msg.author_display);
  const avatarBg = msg.is_admin ? "#6366f1" : avatarColorFor(msg.author_display);
  return (
    <li className={`review-msg ${sideClass}`}>
      <div className="review-msg-avatar" style={{ background: avatarBg }}>{avatar}</div>
      <div className="review-msg-content">
        <div className="review-msg-head">
          <span className="review-msg-author">
            {msg.author_display}
            {msg.is_admin && <span className="review-msg-badge">Argus 官方</span>}
          </span>
          <span className="review-msg-time" title={new Date(msg.created_at).toLocaleString("zh-Hant")}>
            {formatRelativeTime(msg.created_at)}
          </span>
        </div>
        {msg.body && <p className="review-msg-body">{msg.body}</p>}
        {msg.image_url && (
          <button
            type="button"
            className="review-msg-image-btn"
            onClick={() => onImageClick(msg.image_url)}
          >
            <img src={msg.image_url} alt="附件" className="review-msg-image" />
          </button>
        )}
        <div className="review-msg-actions">
          <button
            type="button"
            className={`helpful-btn ${msg.my_helpful ? "active" : ""}`}
            onClick={() => onHelpful(msg)}
          >
            👍 有幫助 {msg.helpful_count > 0 && <span>· {msg.helpful_count}</span>}
          </button>
        </div>
      </div>
    </li>
  );
}

function ReviewMessageComposer({ reviewId, onPosted }) {
  const [body, setBody] = useState("");
  const [imageFile, setImageFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    if (!body.trim() && !imageFile) {
      setError("請輸入文字或附上圖片");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const formData = new FormData();
      if (body.trim()) formData.append("body", body.trim());
      if (imageFile) formData.append("image", imageFile);
      await api.post(`/reviews/${reviewId}/messages/`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setBody("");
      setImageFile(null);
      onPosted?.();
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
          err?.response?.data?.non_field_errors?.[0] ||
          "送出失敗，請稍後再試。",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="review-composer" onSubmit={handleSubmit}>
      <textarea
        className="input review-composer-input"
        placeholder="補充說明或回覆管理員…"
        rows={2}
        value={body}
        onChange={(e) => setBody(e.target.value)}
      />
      <div className="review-composer-row">
        <label className="review-composer-image">
          📎 附圖
          <input
            type="file"
            accept="image/*"
            onChange={(e) => setImageFile(e.target.files?.[0] || null)}
          />
        </label>
        {imageFile && (
          <span className="review-composer-filename" title={imageFile.name}>
            {imageFile.name}
            <button
              type="button"
              className="review-composer-clear"
              onClick={() => setImageFile(null)}
              aria-label="移除附圖"
            >×</button>
          </span>
        )}
        <button className="primary-button" type="submit" disabled={busy}>
          {busy ? "送出中…" : "送出"}
        </button>
      </div>
      {error && <p className="review-composer-error">{error}</p>}
    </form>
  );
}

function ReviewCard({ review, onHelpful, onMessageHelpful, onImageClick, onPosted, loggedIn }) {
  const [expanded, setExpanded] = useState(review.is_mine);
  const messageCount = (review.messages || []).length;
  const avatarBg = avatarColorFor(review.user_display);
  return (
    <article
      className={[
        "review-card",
        review.is_mine ? "is-mine" : "",
        review.is_featured ? "is-featured" : "",
      ].filter(Boolean).join(" ")}
    >
      {review.is_featured && (
        <span className="review-featured-ribbon">⭐ 精選評論</span>
      )}
      <header className="review-card-head">
        <div className="review-card-author-row">
          <div className="review-card-avatar" style={{ background: avatarBg }}>
            {getAvatarLetter(review.user_display)}
          </div>
          <div className="review-card-author-meta">
            <div className="review-card-author">
              {review.user_display}
              {review.is_mine && <span className="review-mine-chip">我</span>}
              {review.verified_buyer && <span className="review-verified-chip">✓ 已購買</span>}
            </div>
            <div className="review-card-time" title={new Date(review.created_at).toLocaleString("zh-Hant")}>
              {formatRelativeTime(review.created_at)}
            </div>
          </div>
        </div>
        <StarRating value={review.rating} readOnly size={20} />
      </header>

      {review.comment && (
        <p className="review-card-body">{review.comment}</p>
      )}

      <div className="review-card-actions">
        <button
          type="button"
          className={`helpful-btn ${review.my_helpful ? "active" : ""}`}
          onClick={() => onHelpful(review)}
          disabled={!loggedIn}
          title={loggedIn ? "" : "請先登入"}
        >
          👍 有幫助 {review.helpful_count > 0 && <span>· {review.helpful_count}</span>}
        </button>
        {messageCount > 0 && (
          <button
            type="button"
            className="thread-toggle-btn"
            onClick={() => setExpanded((v) => !v)}
          >
            💬 {messageCount} 則對話 {expanded ? "▴" : "▾"}
          </button>
        )}
      </div>

      {expanded && (
        <ol className="review-thread">
          {(review.messages || []).map((m) => (
            <ReviewMessageBubble
              key={m.id}
              msg={m}
              onHelpful={(msg) => onMessageHelpful(msg)}
              onImageClick={onImageClick}
            />
          ))}
        </ol>
      )}

      {loggedIn && review.is_mine && (
        <ReviewMessageComposer
          reviewId={review.id}
          onPosted={() => { onPosted?.(); setExpanded(true); }}
        />
      )}
    </article>
  );
}

function ReviewsPage() {
  const [reviews, setReviews] = useState([]);
  const [mine, setMine] = useState(null);
  const [initialRating, setInitialRating] = useState(0);
  const [initialComment, setInitialComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [sort, setSort] = useState("helpful");
  const [lightboxUrl, setLightboxUrl] = useState(null);
  const accessToken = useArgusStore((s) => s.accessToken);

  async function loadAll() {
    const list = await api.get(`/reviews/?sort=${sort}`).catch(() => null);
    if (list) setReviews(list.data.reviews || []);
    if (accessToken) {
      try {
        const me = await api.get("/reviews/mine/");
        setMine(me.data);
      } catch {
        setMine(null);
      }
    }
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, sort]);

  async function handleReviewHelpful(review) {
    if (!accessToken) return;
    try {
      const r = await api.post(`/reviews/${review.id}/helpful/`);
      setReviews((rs) => rs.map((x) =>
        x.id === review.id
          ? { ...x, helpful_count: r.data.helpful_count, my_helpful: r.data.my_helpful }
          : x,
      ));
    } catch {}
  }

  async function handleMessageHelpful(msg) {
    if (!accessToken) return;
    try {
      const r = await api.post(`/reviews/messages/${msg.id}/helpful/`);
      setReviews((rs) => rs.map((x) => ({
        ...x,
        messages: (x.messages || []).map((m) =>
          m.id === msg.id
            ? { ...m, helpful_count: r.data.helpful_count, my_helpful: r.data.my_helpful }
            : m,
        ),
      })));
    } catch {}
  }

  async function handleFirstReview(event) {
    event.preventDefault();
    if (!initialRating) {
      setFeedback({ tone: "bad", message: "請選擇 1-5 星" });
      return;
    }
    setSubmitting(true);
    setFeedback(null);
    try {
      const response = await api.post("/reviews/mine/", {
        rating: initialRating,
        comment: initialComment,
      });
      setMine(response.data);
      setFeedback({ tone: "good", message: "評論已送出，感謝你！" });
      await loadAll();
    } catch (err) {
      setFeedback({
        tone: "bad",
        message: err?.response?.data?.detail || "送出失敗，請稍後再試。",
      });
    } finally {
      setSubmitting(false);
    }
  }

  const total = reviews.length;
  const avg = total
    ? (reviews.reduce((s, r) => s + r.rating, 0) / total).toFixed(2)
    : null;
  const distribution = [5, 4, 3, 2, 1].map((star) => ({
    star,
    count: reviews.filter((r) => r.rating === star).length,
  }));

  return (
    <section className="panel space-y-4">
      <div>
        <p className="eyebrow">使用者評論</p>
        <h1 className="section-title">大家對 Argus 的評價</h1>
        <p className="mt-1 text-xs text-slate-500">
          星等一人只能評一次（送出後鎖定）；後續可在留言區補充意見、附上問題照片，與管理員對話。
        </p>
      </div>

      <div className="reviews-stats">
        <div className="reviews-avg">
          <div className="reviews-avg-value">{avg ?? "—"}</div>
          <StarRating value={avg ? Math.round(avg) : 0} readOnly size={20} />
          <p className="reviews-avg-meta">共 {total} 則評論</p>
        </div>
        <div className="reviews-distribution">
          {distribution.map((d) => {
            const pct = total ? (d.count / total) * 100 : 0;
            return (
              <div key={d.star} className="reviews-dist-row">
                <span className="reviews-dist-label">{d.star} ★</span>
                <div className="reviews-dist-track">
                  <div
                    className="reviews-dist-fill"
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className="reviews-dist-count">{d.count}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* 還沒評過的人才看到評分表單 */}
      {accessToken && !mine && (
        <form className="reviews-form" onSubmit={handleFirstReview}>
          <p className="reviews-form-title">寫下你對 Argus 的評價（一次定終生）</p>
          <StarRating value={initialRating} onChange={setInitialRating} size={32} />
          <textarea
            className="input reviews-textarea"
            placeholder="（選填）你最喜歡的功能、改進建議..."
            rows={3}
            value={initialComment}
            onChange={(e) => setInitialComment(e.target.value)}
          />
          {feedback && (
            <p className={`reviews-feedback tone-${feedback.tone}`}>
              {feedback.message}
            </p>
          )}
          <button className="primary-button" type="submit" disabled={submitting}>
            {submitting ? "送出中..." : "送出評論"}
          </button>
        </form>
      )}

      {accessToken && mine && (
        <div className="reviews-mine-banner">
          <span>
            ✓ 你已為 Argus 評分 <strong>{"★".repeat(mine.rating)}{"☆".repeat(5 - mine.rating)}</strong>（{mine.rating}）
          </span>
          <span className="text-xs text-slate-500">
            如要補充意見，請在下方自己的評論卡裡留言。
          </span>
        </div>
      )}

      <div className="reviews-toolbar">
        <span className="text-sm text-slate-600">共 {reviews.length} 則評論</span>
        <div className="reviews-sort">
          <button
            type="button"
            className={`reviews-sort-btn ${sort === "helpful" ? "active" : ""}`}
            onClick={() => setSort("helpful")}
          >最有幫助</button>
          <button
            type="button"
            className={`reviews-sort-btn ${sort === "newest" ? "active" : ""}`}
            onClick={() => setSort("newest")}
          >最新</button>
        </div>
      </div>

      <div className="reviews-list">
        {reviews.length === 0 && (
          <p className="hint-text">尚未有評論。第一個寫下評價吧！</p>
        )}
        {reviews.map((review) => (
          <ReviewCard
            key={review.id}
            review={review}
            loggedIn={!!accessToken}
            onHelpful={handleReviewHelpful}
            onMessageHelpful={handleMessageHelpful}
            onImageClick={setLightboxUrl}
            onPosted={loadAll}
          />
        ))}
      </div>

      <ImageLightbox url={lightboxUrl} onClose={() => setLightboxUrl(null)} />
    </section>
  );
}

// ============================================================
// Settings 頁
// ============================================================

function SettingsPage() {
  const navigate = useNavigate();
  const wallet = useArgusStore((s) => s.wallet);
  const [data, setData] = useState(null);

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");

  const [oldPwd, setOldPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const [pwdMsg, setPwdMsg] = useState("");
  const [pwdError, setPwdError] = useState("");

  const [meData, setMeData] = useState(null);
  useEffect(() => {
    api.get("/auth/me/").then((r) => {
      setMeData(r.data);
      setFirstName(r.data.first_name || "");
      setLastName(r.data.last_name || "");
    }).catch(() => {});
    api.get("/dashboard/").then((r) => setData(r.data)).catch(() => {});
  }, []);

  const balance = wallet?.balance ?? 0;
  const purchased = wallet?.total_purchased_ntd ?? 0;
  const scansUsed = wallet?.total_scans_used ?? 0;
  const totalFindings = data
    ? Object.values(data.severity_totals || {}).reduce((sum, n) => sum + n, 0)
    : 0;
  const isEmailAccount = meData?.auth_provider === "email";

  async function handleSaveProfile(e) {
    e.preventDefault();
    setSaving(true);
    setSaveMsg("");
    try {
      await api.patch("/auth/me/", { first_name: firstName, last_name: lastName });
      setSaveMsg("已儲存");
    } catch {
      setSaveMsg("儲存失敗");
    } finally {
      setSaving(false);
    }
  }

  async function handleChangePassword(e) {
    e.preventDefault();
    setPwdError("");
    setPwdMsg("");
    if (newPwd !== confirmPwd) { setPwdError("兩次密碼不一致"); return; }
    if (newPwd.length < 8) { setPwdError("新密碼至少 8 個字元"); return; }
    try {
      await api.post("/auth/change-password/", { old_password: oldPwd, new_password: newPwd });
      setPwdMsg("密碼已更新");
      setOldPwd(""); setNewPwd(""); setConfirmPwd("");
    } catch (err) {
      setPwdError(err.response?.data?.detail || "密碼變更失敗");
    }
  }

  return (
    <div className="settings-page">
      <h1 className="settings-title">帳號設定</h1>

      <section className="settings-section">
        <h2 className="settings-section-title">點數錢包</h2>
        <div className="settings-wallet-row">
          <div>
            <p className="settings-wallet-balance">{balance} <span className="settings-wallet-unit">coin</span></p>
            <p className="settings-card-hint">累積購買 NT$ {purchased.toLocaleString()} · 累計 {scansUsed} 次掃描</p>
          </div>
          <button className="settings-save-btn" type="button" onClick={() => navigate("/billing")}>前往購點</button>
        </div>
      </section>

      <section className="settings-section">
        <h2 className="settings-section-title">個人資料</h2>
        <form className="settings-form" onSubmit={handleSaveProfile}>
          <div className="settings-field">
            <label>Email</label>
            <p className="settings-field-value">{meData?.email || meData?.username}</p>
          </div>
          <div className="settings-field">
            <label>名字</label>
            <input className="input" value={firstName} onChange={(e) => setFirstName(e.target.value)} placeholder="名" />
          </div>
          <div className="settings-field">
            <label>姓氏</label>
            <input className="input" value={lastName} onChange={(e) => setLastName(e.target.value)} placeholder="姓" />
          </div>
          <button className="settings-save-btn" type="submit" disabled={saving}>
            {saving ? "儲存中…" : "儲存變更"}
          </button>
          {saveMsg && <p className="settings-msg">{saveMsg}</p>}
        </form>
      </section>

      <section className="settings-section">
        <h2 className="settings-section-title">登入方式</h2>
        <p className="settings-field-value">
          {isEmailAccount ? "Email 帳號" : "Google 帳號（透過 Google 管理密碼）"}
        </p>
      </section>

      {isEmailAccount && (
        <section className="settings-section">
          <h2 className="settings-section-title">更改密碼</h2>
          <form className="settings-form" onSubmit={handleChangePassword}>
            <input className="input" type="password" placeholder="目前密碼" value={oldPwd} onChange={(e) => setOldPwd(e.target.value)} autoComplete="current-password" />
            <input className="input" type="password" placeholder="新密碼（至少 8 字元）" value={newPwd} onChange={(e) => setNewPwd(e.target.value)} autoComplete="new-password" />
            <input className="input" type="password" placeholder="確認新密碼" value={confirmPwd} onChange={(e) => setConfirmPwd(e.target.value)} autoComplete="new-password" />
            {pwdError && <p className="settings-error">{pwdError}</p>}
            {pwdMsg && <p className="settings-msg">{pwdMsg}</p>}
            <button className="settings-save-btn" type="submit">更新密碼</button>
          </form>
        </section>
      )}

      <section className="settings-section settings-danger-zone">
        <h2 className="settings-section-title danger">危險操作</h2>
        <p className="settings-danger-desc">刪除帳號將移除所有掃描紀錄與點數，此操作無法復原。</p>
        <button
          className="settings-danger-btn"
          type="button"
          onClick={() => {
            if (window.confirm("確定要刪除帳號嗎？此操作無法復原。")) {
              alert("請聯絡管理員協助刪除帳號。");
            }
          }}
        >
          刪除帳號
        </button>
      </section>
    </div>
  );
}

// ============================================================
// 公開頁面（PublicLayout + /project /team /purchase /download）
// 不需登入即可瀏覽，獨立 nav，PWA 真實可安裝。
// ============================================================

const PUBLIC_NAV_ITEMS = [
  { to: "/project", label: "專案介紹" },
  { to: "/free-tools", label: "快速檢查" },
  { to: "/team", label: "團隊" },
  { to: "/purchase", label: "購買" },
  { to: "/download", label: "下載" },
  { to: "/reviews", label: "評論" },
];

function PublicNav() {
  const accessToken = useArgusStore((s) => s.accessToken);
  const replayIntro = useArgusStore((s) => s.replayIntro);
  const theme = useArgusStore((s) => s.theme);
  const toggleTheme = useArgusStore((s) => s.toggleTheme);
  return (
    <nav className="public-nav">
      <div className="public-nav-inner">
        <button type="button" className="public-brand active" onClick={replayIntro} title="重播開場動畫" aria-label="重播 ARGUS 開場動畫">
          <img src={brandLogo} className="public-brand-logo" alt="ARGUS — AI 網站健檢平台" />
          <span className="public-brand-sub">AI 網站健檢平台</span>
        </button>
        <div className="public-nav-links">
          {PUBLIC_NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `public-nav-link ${isActive ? "active" : ""}`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </div>
        <div className="public-nav-cta">
          <button
            type="button"
            className="theme-toggle"
            onClick={toggleTheme}
            title="切換深色 / 淺色主題"
            aria-label="切換深色 / 淺色主題"
          >
            <span className="theme-toggle-icon" aria-hidden="true">
              {theme === "light" ? "☾" : "☀"}
            </span>
            <span>{theme === "light" ? "夜間" : "日間"}</span>
          </button>
          {accessToken ? (
            <NavLink to="/dashboard" className="public-cta-primary">
              進入 Dashboard
            </NavLink>
          ) : (
            <NavLink to="/login" className="public-cta-primary">
              登入 / 註冊
            </NavLink>
          )}
        </div>
      </div>
    </nav>
  );
}

function PublicFooter() {
  return (
    <footer className="public-footer">
      <div className="public-footer-inner">
        <div>
          <div className="public-footer-brand">⟡ ARGUS</div>
          <div className="public-footer-sub">授權式 AI 網站健檢平台</div>
        </div>
        <div className="public-footer-links">
          <NavLink to="/project">專案介紹</NavLink>
          <NavLink to="/team">團隊</NavLink>
          <NavLink to="/purchase">購買</NavLink>
          <NavLink to="/download">下載 PWA</NavLink>
          <NavLink to="/reviews">評論</NavLink>
        </div>
        <div className="public-footer-copy">
          © Argus · 僅供授權測試的網站健檢工具
        </div>
      </div>
    </footer>
  );
}

function PublicLayout() {
  return (
    <div className="public-shell">
      <PublicNav />
      <main className="public-main">
        <Outlet />
      </main>
      <PublicFooter />
    </div>
  );
}

// useInstallPrompt：取得 PWA 安裝能力。事件在 main.jsx 已全域捕捉到 window，
// 這裡讀回並監聽後續事件，避免「事件在元件掛載前觸發」的 race。
function isStandalone() {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    window.navigator.standalone === true
  );
}
function useInstallPrompt() {
  const [deferred, setDeferred] = useState(() => window.__argusInstallPrompt || null);
  const [installed, setInstalled] = useState(() => !!window.__argusInstalled || isStandalone());
  useEffect(() => {
    function onPrompt(e) {
      e.preventDefault();
      window.__argusInstallPrompt = e;
      setDeferred(e);
    }
    function onInstallable() {
      setDeferred(window.__argusInstallPrompt);
    }
    function onInstalled() {
      setInstalled(true);
      setDeferred(null);
    }
    // 掛載時若全域已捕捉到事件，立即採用（修正 race）
    if (window.__argusInstallPrompt) setDeferred(window.__argusInstallPrompt);
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("argus-installable", onInstallable);
    window.addEventListener("appinstalled", onInstalled);
    window.addEventListener("argus-installed", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("argus-installable", onInstallable);
      window.removeEventListener("appinstalled", onInstalled);
      window.removeEventListener("argus-installed", onInstalled);
    };
  }, []);
  async function trigger() {
    const d = deferred || window.__argusInstallPrompt;
    if (!d) return null;
    d.prompt();
    const { outcome } = await d.userChoice;
    window.__argusInstallPrompt = null;
    setDeferred(null);
    return outcome;
  }
  return { canInstall: !!deferred, installed, trigger };
}

const TECH_STACK_CHIPS = [
  { label: "React 18", colour: "#06b6d4" },
  { label: "Vite", colour: "#a855f7" },
  { label: "Tailwind", colour: "#22d3ee" },
  { label: "Zustand", colour: "#f97316" },
  { label: "Django 5", colour: "#0ea5e9" },
  { label: "DRF", colour: "#dc2626" },
  { label: "Celery", colour: "#10b981" },
  { label: "Playwright", colour: "#84cc16" },
  { label: "PostgreSQL", colour: "#3b82f6" },
  { label: "Docker", colour: "#0284c7" },
  { label: "PWA", colour: "#6366f1" },
];

const PROJECT_PLATFORM_STATS = [
  { label: "Django Apps", value: "8", hint: "accounts / scans / agent / billing / reviews / admin_api / content / insights" },
  { label: "資料模型", value: "20+", hint: "ScanJob、Finding、CoinWallet、PurchaseOrder…" },
  { label: "自動化測試", value: "250+", hint: "API / 權限 / billing 流程 / 圖片上傳" },
  { label: "REST 端點", value: "40+", hint: "billing / reviews / content / admin / scans / insights" },
];

function ProjectScanDemo() {
  return (
    <div className="project-demo">
      <div className="project-demo-window">
        <div className="project-demo-title-bar">
          <span className="project-demo-dot project-demo-dot-r" />
          <span className="project-demo-dot project-demo-dot-y" />
          <span className="project-demo-dot project-demo-dot-g" />
          <span className="project-demo-url">argus.example.com / 掃描中…</span>
        </div>
        <div className="project-demo-body">
          <div className="project-demo-phase">
            <span className="project-demo-phase-icon">🕷️</span>
            <span>爬蟲中… 12 / 50 頁</span>
            <span className="project-demo-progress">
              <span className="project-demo-progress-fill" />
            </span>
          </div>
          <ul className="project-demo-findings">
            <li className="project-demo-finding sev-high">
              <span className="project-demo-finding-sev">HIGH</span>
              <span className="project-demo-finding-title">頁面未使用 HTTPS</span>
            </li>
            <li className="project-demo-finding sev-medium">
              <span className="project-demo-finding-sev">MED</span>
              <span className="project-demo-finding-title">缺少 JSON-LD 結構化資料</span>
            </li>
            <li className="project-demo-finding sev-low">
              <span className="project-demo-finding-sev">LOW</span>
              <span className="project-demo-finding-title">圖片缺 alt 屬性 ×3</span>
            </li>
            <li className="project-demo-finding sev-info">
              <span className="project-demo-finding-sev">INFO</span>
              <span className="project-demo-finding-title">建議加 llms.txt 給 AI 爬蟲</span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}

// 後台 CMS 可編輯前，先用這份 fallback；API 拉到資料就會覆蓋掉
const PROJECT_FEATURES_FALLBACK = [
  { id: -1, icon: "🕷️", title: "BFS 深度爬蟲", description: "以 Playwright 驅動的 BFS 爬蟲，自動探索整站結構。" },
  { id: -2, icon: "🔍", title: "四維安全掃描", description: "涵蓋 SEO、AEO、GEO、Security 四個維度的全面分析。" },
  { id: -3, icon: "🤖", title: "Hermes AI Agent", description: "LLM 驅動的智慧代理人，提供主動式漏洞驗證。" },
  { id: -4, icon: "📊", title: "即時進度追蹤", description: "掃描進度即時更新，支援多任務並行管理。" },
  { id: -5, icon: "📝", title: "Word 報告匯出", description: "一鍵產生專業 Word 格式掃描報告，方便交付客戶。" },
  { id: -6, icon: "💎", title: "點數計費系統", description: "靈活的 Coin 計費模式，按頁計費，精準控制成本。" },
];

function ProjectPage() {
  const [features, setFeatures] = useState(PROJECT_FEATURES_FALLBACK);
  const [milestones, setMilestones] = useState([]);
  useEffect(() => {
    api.get("/content/features/")
      .then((r) => {
        const list = r.data.features || [];
        if (list.length) setFeatures(list);
      })
      .catch(() => {});
    api.get("/content/milestones/").then((r) => setMilestones(r.data.milestones || [])).catch(() => {});
  }, []);
  return (
    <div className="public-page">
      <section className="public-hero public-hero--console">
        <div className="public-hero-bg" aria-hidden="true">
          <span className="hero-orb hero-orb-1" />
          <span className="hero-orb hero-orb-2" />
          <span className="hero-orb hero-orb-3" />
          <span className="hero-grid" />
          <span className="hero-scan" />
          <span className="hero-corner tl" />
          <span className="hero-corner tr" />
          <span className="hero-corner bl" />
          <span className="hero-corner br" />
        </div>
        <div className="public-hero-content">
          <img src={brandLogo} className="public-hero-logo" alt="ARGUS" />
          <span className="public-hero-eyebrow">掃描 · 洞察 · 證據</span>
          <h1 className="public-hero-title">
            一鍵看見<span className="hero-grad">網站的所有問題</span>
          </h1>
          <p className="public-hero-sub">
            把網站問題整理成可以執行的改善順序。
            整合全站爬蟲、四維靜態掃描與 LLM Agent 行為測試，
            為你授權的網站產出可互動報告與 Word 文件，
            並輸出結構化 Prompt 帶去 ChatGPT / Claude 取得修補方向。
          </p>
          <div className="public-hero-actions">
            <NavLink to="/login" className="public-cta-primary">登入進行詳細檢查 →</NavLink>
            <NavLink to="/download" className="public-cta-ghost">下載 PWA</NavLink>
          </div>
        </div>
      </section>

      <section className="public-section">
        <header className="public-section-head">
          <h2>安全邊界</h2>
          <p>不是文宣口號，每一項都對應實際程式碼</p>
        </header>
        <div className="public-feature-grid">
          <article className="public-feature-card">
            <div className="public-feature-icon">🔐</div>
            <h3 className="public-feature-title">授權確認</h3>
            <p className="public-feature-desc">
              每次任務記錄 IP、時間、User-Agent 與授權勾選狀態；第三方或敏感網域要求二次確認。
            </p>
          </article>
          <article className="public-feature-card">
            <div className="public-feature-icon">🌐</div>
            <h3 className="public-feature-title">同網域邏輯</h3>
            <p className="public-feature-desc">
              爬蟲與 finding 證據只限授權目標的同網域頁面，不會跨域追蹤或污染他站。
            </p>
          </article>
          <article className="public-feature-card">
            <div className="public-feature-icon">🛡️</div>
            <h3 className="public-feature-title">SSRF 防護（已實作）</h3>
            <p className="public-feature-desc">
              阻擋 localhost、私網段、雲端 metadata、IP 字面，且逐跳 redirect 都重新檢查目標主機。
            </p>
          </article>
          <article className="public-feature-card">
            <div className="public-feature-icon">👀</div>
            <h3 className="public-feature-title">預設被動模式</h3>
            <p className="public-feature-desc">
              Phase 1 不做破壞性或主動式漏洞攻擊；主動模式需額外勾選且記入稽核軌跡。
            </p>
          </article>
        </div>
      </section>

      <section className="public-section">
        <header className="public-section-head">
          <h2>平台規模</h2>
          <p>不是 demo 玩具，是真實量產規格</p>
        </header>
        <div className="project-stats-grid">
          {PROJECT_PLATFORM_STATS.map((s) => (
            <div key={s.label} className="project-stat-card">
              <div className="project-stat-value">{s.value}</div>
              <div className="project-stat-label">{s.label}</div>
              <div className="project-stat-hint">{s.hint}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="public-section">
        <header className="public-section-head">
          <h2>它怎麼運作</h2>
          <p>輸入網址 → 爬蟲 → 四維掃描 → 互動報告</p>
        </header>
        <ProjectScanDemo />
      </section>

      <section className="public-section">
        <header className="public-section-head">
          <h2>核心功能</h2>
          <p>從爬蟲到 LLM Agent，端到端解決方案</p>
        </header>
        <div className="public-feature-grid">
          {features.map((f) => (
            <article key={f.id} className="public-feature-card">
              <div className="public-feature-icon">{f.icon || "✨"}</div>
              <h3 className="public-feature-title">{f.title}</h3>
              <p className="public-feature-desc">{f.description}</p>
            </article>
          ))}
          {features.length === 0 && (
            <p className="public-empty">尚未設定功能介紹。</p>
          )}
        </div>
      </section>

      {milestones.length > 0 && (
        <section className="public-section">
          <header className="public-section-head">
            <h2>開發歷程</h2>
            <p>從 MVP 到上線的關鍵里程碑</p>
          </header>
          <ol className="project-timeline">
            {milestones.map((m, idx) => (
              <li key={m.id} className={`project-timeline-item ${idx === 0 ? "is-first" : ""}`}>
                <div className="project-timeline-marker">
                  <span className="project-timeline-icon">{m.icon || "🚩"}</span>
                </div>
                <div className="project-timeline-body">
                  <div className="project-timeline-date">
                    {new Date(m.date).toLocaleDateString("zh-Hant", { year: "numeric", month: "long", day: "numeric" })}
                  </div>
                  <div className="project-timeline-title">{m.title}</div>
                  {m.description && (
                    <p className="project-timeline-desc">{m.description}</p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="public-section">
        <header className="public-section-head">
          <h2>技術棧</h2>
          <p>不偷工，全棧現代化選型</p>
        </header>
        <div className="public-tech-chips">
          {TECH_STACK_CHIPS.map((t) => (
            <span
              key={t.label}
              className="public-tech-chip"
              style={{ borderColor: t.colour + "60", "--chip-color": t.colour }}
            >{t.label}</span>
          ))}
        </div>
      </section>

      <section className="public-section public-final-cta-wrap">
        <div className="public-final-cta">
          <div>
            <h2 className="public-final-cta-title">準備好健檢你的網站了嗎？</h2>
            <p className="public-final-cta-sub">想先試用？「快速檢查」免登入、不扣點；登入後每月自動贈 200 coin，掃描依實際頁數計點。</p>
          </div>
          <NavLink to="/purchase" className="public-cta-primary public-final-cta-btn">
            查看方案 →
          </NavLink>
        </div>
      </section>
    </div>
  );
}

function TeamMemberCard({ member }) {
  const m = member;
  return (
    <article className="public-team-card-pro">
      <header className="public-team-card-head">
        <div className="public-team-avatar-wrap">
          <span className="public-team-avatar-ring" aria-hidden="true" />
          <span className="public-team-avatar-glyph">{m.avatar_emoji || "🧑"}</span>
        </div>
        <div className="public-team-card-meta">
          <div className="public-team-name">{m.name}</div>
          <div className="public-team-role">{m.role}</div>
          {m.student_id && (
            <div className="public-team-id-badge">🎓 學號 {m.student_id}</div>
          )}
          {m.bio && <p className="public-team-bio">{m.bio}</p>}
        </div>
      </header>

      {Array.isArray(m.skill_levels) && m.skill_levels.length > 0 && (
        <div className="public-team-skill-bars">
          <div className="public-team-block-label">⚡ 技能熟練度</div>
          {m.skill_levels.map((s) => (
            <div key={s.name} className="public-team-skill-row">
              <div className="public-team-skill-row-head">
                <span>{s.name}</span>
                <span className="public-team-skill-pct">{s.level}%</span>
              </div>
              <div className="public-team-skill-track">
                <div
                  className="public-team-skill-fill"
                  style={{ width: `${Math.max(0, Math.min(100, s.level))}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {Array.isArray(m.contributions) && m.contributions.length > 0 && (
        <div className="public-team-contrib">
          <div className="public-team-contrib-label">🎯 負責項目</div>
          <ul className="public-team-contrib-list">
            {m.contributions.map((c, i) => (
              <li key={i}>
                <span className="public-team-contrib-bullet" aria-hidden="true" />
                <div>
                  <div className="public-team-contrib-title">{c.title}</div>
                  {c.desc && <div className="public-team-contrib-desc">{c.desc}</div>}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {Array.isArray(m.skills) && m.skills.length > 0 && (
        <div className="public-team-skills">
          <div className="public-team-block-label public-team-skills-label">🧩 技術棧</div>
          {m.skills.map((s) => (
            <span key={s} className="public-team-skill-chip">{s}</span>
          ))}
        </div>
      )}

      {(m.email || m.github_url) && (
        <div className="public-team-links">
          {m.email && <a href={`mailto:${m.email}`}>✉ {m.email}</a>}
          {m.github_url && (
            <a href={m.github_url} target="_blank" rel="noopener noreferrer">
              🐙 GitHub
            </a>
          )}
        </div>
      )}
    </article>
  );
}

function TeamPage() {
  const [members, setMembers] = useState([]);
  useEffect(() => {
    api.get("/content/team/").then((r) => setMembers(r.data.members || [])).catch(() => {});
  }, []);
  return (
    <div className="public-page">
      <section className="public-hero compact">
        <div className="public-hero-bg" aria-hidden="true">
          <span className="hero-orb hero-orb-1" />
          <span className="hero-orb hero-orb-2" />
          <span className="hero-orb hero-orb-3" />
        </div>
        <div className="public-hero-content">
          <span className="public-hero-eyebrow">TEAM · 團隊</span>
          <h1 className="public-hero-title">
            打造 Argus 的<span className="hero-grad">團隊</span>
          </h1>
          <p className="public-hero-sub">
            {members.length} 位成員跨領域協作，從 Playwright 爬蟲、LLM Agent
            到 Tailwind UI 與 Docker 部署，一手包辦。
          </p>
          <div className="public-team-stats">
            <div className="public-team-stat">
              <div className="public-team-stat-value">{members.length}</div>
              <div className="public-team-stat-label">核心成員</div>
            </div>
            <div className="public-team-stat">
              <div className="public-team-stat-value">8</div>
              <div className="public-team-stat-label">Django apps</div>
            </div>
            <div className="public-team-stat">
              <div className="public-team-stat-value">249+</div>
              <div className="public-team-stat-label">自動化測試</div>
            </div>
          </div>
        </div>
      </section>

      <section className="public-section">
        <div className="public-team-grid-pro">
          {members.map((m) => (
            <TeamMemberCard key={m.id} member={m} />
          ))}
          {members.length === 0 && (
            <p className="public-empty">尚未設定團隊成員。</p>
          )}
        </div>
      </section>
    </div>
  );
}

const PURCHASE_FAQ = [
  {
    q: "點數會過期嗎？",
    a: "不會。已購點數永久有效，未使用的點數可一直累積。",
  },
  {
    q: "如何計算所需點數？",
    a: "每爬一個頁面 10 coin。建立掃描時依「最大頁數」預扣，完成後依實際頁數退回未使用的部分。",
  },
  {
    q: "支援哪些付款方式？",
    a: "目前為模擬付款（點選即入帳，供示範用）。正式上線後將串接綠界 / 藍新 / Stripe 等金流。",
  },
  {
    q: "可以退費嗎？",
    a: "如有特殊狀況請聯絡管理員，由 admin 在後台手動退費。掃描失敗或被取消時，系統會自動全額退回預扣的點數。",
  },
];

const COMPARE_ROWS = [
  {
    feature: "全站爬蟲（同網域、深度 3、最多 50 頁）",
    argus: true, self: "技術門檻高", competitor: "通常另計",
  },
  {
    feature: "SEO + AEO + GEO + 資安四維掃描",
    argus: true, self: "工具多套需自己整合", competitor: "多為單一維度",
  },
  {
    feature: "AI Agent 擬真使用者 UX 測試",
    argus: true, self: "無", competitor: "罕見",
  },
  {
    feature: "可互動報告（截圖紅框 + 雙向跳轉）",
    argus: true, self: "Lighthouse 純文字", competitor: "PDF 為主",
  },
  {
    feature: "Word 報告自動匯出",
    argus: true, self: "手寫", competitor: "額外加購",
  },
  {
    feature: "結構化問題 Prompt 帶去 ChatGPT 修",
    argus: true, self: "需要自己整理", competitor: "—",
  },
  {
    feature: "按頁付費（用多少付多少）",
    argus: true, self: "—", competitor: "月費綁約",
  },
  {
    feature: "首月免費 200 coin",
    argus: true, self: "—", competitor: "需信用卡綁定試用",
  },
];

function PurchasePage() {
  const [openFaq, setOpenFaq] = useState(0);
  const navigate = useNavigate();
  return (
    <div className="public-page">
      <section className="public-hero compact">
        <div className="public-hero-bg" aria-hidden="true">
          <span className="hero-orb hero-orb-1" />
          <span className="hero-orb hero-orb-2" />
          <span className="hero-orb hero-orb-3" />
        </div>
        <div className="public-hero-content">
          <span className="public-hero-eyebrow">PRICING · 為什麼選 Argus</span>
          <h1 className="public-hero-title">
            <span className="hero-grad">按頁付費</span>，永久有效
          </h1>
          <p className="public-hero-sub">
            每爬一頁 10 coin，新會員每月自動贈送 200 coin；買越多越划算，
            點數不會過期，失敗或取消自動全額退回。
          </p>
          <div className="public-hero-actions">
            <button
              type="button"
              className="public-cta-primary"
              onClick={() => navigate("/billing")}
            >
              看方案 + 開始結帳 →
            </button>
          </div>
        </div>
      </section>

      <section className="public-section">
        <header className="public-section-head">
          <h2>為什麼選 Argus</h2>
          <p>我們、自己做、市面其他工具的對比</p>
        </header>
        <div className="public-compare-wrap">
          <table className="public-compare-table">
            <thead>
              <tr>
                <th className="public-compare-feature">功能</th>
                <th className="public-compare-argus">
                  <div className="public-compare-brand">⟡ ARGUS</div>
                </th>
                <th>自己做</th>
                <th>競品工具</th>
              </tr>
            </thead>
            <tbody>
              {COMPARE_ROWS.map((row, idx) => (
                <tr key={idx}>
                  <td className="public-compare-feature">{row.feature}</td>
                  <td className="public-compare-argus">
                    {row.argus === true ? <span className="check-yes">✓</span> : row.argus}
                  </td>
                  <td className="public-compare-cell">{row.self}</td>
                  <td className="public-compare-cell">{row.competitor}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="public-section">
        <header className="public-section-head">
          <h2>常見問題</h2>
        </header>
        <div className="public-faq">
          {PURCHASE_FAQ.map((item, idx) => (
            <details
              key={idx}
              open={openFaq === idx}
              onToggle={(e) => e.target.open && setOpenFaq(idx)}
              className="public-faq-item"
            >
              <summary>{item.q}</summary>
              <p>{item.a}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="public-section public-final-cta-wrap">
        <div className="public-final-cta">
          <div>
            <h2 className="public-final-cta-title">準備好了嗎？</h2>
            <p className="public-final-cta-sub">3 步驟結帳，30 秒入帳，馬上開始健檢你的網站。</p>
          </div>
          <button
            type="button"
            className="public-cta-primary public-final-cta-btn"
            onClick={() => navigate("/billing")}
          >
            前往結帳 →
          </button>
        </div>
      </section>

    </div>
  );
}

const RISK_LABELS = {
  high: "高風險",
  medium: "中風險",
  low: "低風險",
  minimal: "低訊號",
};

function RiskLevelBadge({ level }) {
  return (
    <span className={`insight-risk-badge risk-${level || "minimal"}`}>
      {RISK_LABELS[level] || "未判定"}
    </span>
  );
}

function FreeToolsPage() {
  const [speedForm, setSpeedForm] = useState({
    url: "",
    authorization_confirmed: false,
  });
  const [speedLoading, setSpeedLoading] = useState(false);
  const [speedResult, setSpeedResult] = useState(null);
  const [speedError, setSpeedError] = useState("");
  const [urlValue, setUrlValue] = useState("");
  const [urlLoading, setUrlLoading] = useState(false);
  const [urlResult, setUrlResult] = useState(null);
  const [urlError, setUrlError] = useState("");
  const [emailValue, setEmailValue] = useState("");
  const [emailLoading, setEmailLoading] = useState(false);
  const [emailResult, setEmailResult] = useState(null);
  const [emailError, setEmailError] = useState("");
  const [quickForm, setQuickForm] = useState({ url: "", authorization_confirmed: false });
  const [quickLoading, setQuickLoading] = useState(false);
  const [quickResult, setQuickResult] = useState(null);
  const [quickError, setQuickError] = useState("");
  const [tool, setTool] = useState("scan"); // 免費工具分頁：scan / speed / phish

  const runSpeedTest = async (event) => {
    event.preventDefault();
    setSpeedLoading(true);
    setSpeedError("");
    setSpeedResult(null);
    try {
      const res = await api.post("/insights/speed-test/", speedForm);
      setSpeedResult(res.data);
    } catch (err) {
      setSpeedError(apiErrorMessage(err, "測速失敗，請確認網址可公開連線。"));
    } finally {
      setSpeedLoading(false);
    }
  };

  const runQuickScan = async (event) => {
    event.preventDefault();
    setQuickLoading(true);
    setQuickError("");
    setQuickResult(null);
    try {
      const res = await api.post("/insights/quick-scan/", quickForm);
      setQuickResult(res.data);
    } catch (err) {
      setQuickError(apiErrorMessage(err, "單頁快速檢查失敗，請確認網址可公開連線。"));
    } finally {
      setQuickLoading(false);
    }
  };

  const runUrlCheck = async (event) => {
    event.preventDefault();
    setUrlLoading(true);
    setUrlError("");
    setUrlResult(null);
    try {
      const res = await api.post("/insights/phishing-url/", { url: urlValue });
      setUrlResult(res.data);
    } catch (err) {
      setUrlError(apiErrorMessage(err, "URL 風險分析失敗。"));
    } finally {
      setUrlLoading(false);
    }
  };

  const runEmailCheck = async (event) => {
    event.preventDefault();
    setEmailLoading(true);
    setEmailError("");
    setEmailResult(null);
    try {
      const res = await api.post("/insights/phishing-email/", { raw_email: emailValue });
      setEmailResult(res.data);
    } catch (err) {
      setEmailError(apiErrorMessage(err, "郵件風險分析失敗。"));
    } finally {
      setEmailLoading(false);
    }
  };

  return (
    <div className="public-page free-tools-page">
      <section className="public-hero compact">
        <div className="public-hero-bg" aria-hidden="true">
          <span className="hero-orb hero-orb-1" />
          <span className="hero-orb hero-orb-2" />
          <span className="hero-orb hero-orb-3" />
        </div>
        <div className="public-hero-content">
          <span className="public-hero-eyebrow">QUICK CHECK · 快速檢查</span>
          <h1 className="public-hero-title">
            先用<span className="hero-grad">快速檢查</span>初步判斷
          </h1>
          <p className="public-hero-sub">
            <strong>免登入、不扣點數、即時出結果。</strong>單頁測速參考 PageSpeed / Lighthouse 的效能思路；
            釣魚網址與郵件判斷使用本機特徵分類器，不把內容送到大模型 API。
          </p>
        </div>
      </section>

      <div className="insight-tabs">
        <button type="button" className={`insight-tab ${tool === "scan" ? "active" : ""}`} onClick={() => setTool("scan")}>🩺 單頁檢查</button>
        <button type="button" className={`insight-tab ${tool === "speed" ? "active" : ""}`} onClick={() => setTool("speed")}>⚡ 網站測速</button>
        <button type="button" className={`insight-tab ${tool === "phish" ? "active" : ""}`} onClick={() => setTool("phish")}>🛡️ 釣魚偵測</button>
      </div>

      {tool === "scan" && (
      <section className="public-section">
        <header className="public-section-head">
          <h2>單頁快速檢查</h2>
          <p>輸入一個網址，立即看 SEO / 資安 / AEO·GEO 的單頁體檢分數與重點問題；完整多頁＋AI 深掃請登入後到「掃描」</p>
        </header>
        <div className="insight-tool-layout">
          <form className="insight-tool-card" onSubmit={runQuickScan}>
            <h3 className="insight-card-title">單頁快速檢查</h3>
            <label className="insight-field">
              <span>網址</span>
              <input
                value={quickForm.url}
                onChange={(e) => setQuickForm((f) => ({ ...f, url: e.target.value }))}
                placeholder="https://example.com/"
                required
              />
            </label>
            <label className="insight-check">
              <input
                type="checkbox"
                checked={quickForm.authorization_confirmed}
                onChange={(e) => setQuickForm((f) => ({ ...f, authorization_confirmed: e.target.checked }))}
              />
              <span>我確認此頁面可公開檢測，或我擁有分析授權。</span>
            </label>
            {quickError && <div className="insight-error">{quickError}</div>}
            <button type="submit" className="public-cta-primary" disabled={quickLoading}>
              {quickLoading ? "檢查中..." : "開始單頁檢查"}
            </button>
          </form>

          <div className="insight-result-card">
            {!quickResult ? (
              <div className="insight-empty">
                <strong>會輸出哪些結果</strong>
                <span>整體分數 + SEO / 資安 / AEO·GEO 三維單頁分數與重點問題清單。</span>
              </div>
            ) : (
              <>
                <div className="insight-score-row">
                  <div className={`insight-score score-${quickResult.grade}`}>
                    {quickResult.overall_score}
                  </div>
                  <div>
                    <div className="insight-result-title">{quickResult.final_url}</div>
                    <div className="insight-result-sub">單頁快速檢查（不含多頁爬蟲 / Playwright）</div>
                  </div>
                </div>
                <div className="insight-metrics-grid">
                  {quickResult.categories.map((c) => (
                    <div key={c.key}><span>{c.label}</span><strong>{c.score}</strong></div>
                  ))}
                </div>
                {quickResult.findings.length > 0 ? (
                  <ul className="insight-finding-list">
                    {quickResult.findings.map((f, idx) => (
                      <li key={`${f.title}-${idx}`}>
                        <strong>{f.title}</strong>
                        <span>{f.detail}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="insight-success">單頁檢查未發現明顯問題。</div>
                )}
                <p className="insight-note">{quickResult.note}</p>
              </>
            )}
          </div>
        </div>
      </section>
      )}

      {tool === "speed" && (
      <section className="public-section">
        <header className="public-section-head">
          <h2>網站測速分析</h2>
          <p>單一 URL、單次請求，不扣 coin，不啟動全站爬蟲</p>
        </header>
        <div className="insight-tool-layout">
          <form className="insight-tool-card" onSubmit={runSpeedTest}>
            <label className="insight-field">
              <span>網址</span>
              <input
                value={speedForm.url}
                onChange={(e) => setSpeedForm((f) => ({ ...f, url: e.target.value }))}
                placeholder="https://example.com/"
                required
              />
            </label>
            <label className="insight-check">
              <input
                type="checkbox"
                checked={speedForm.authorization_confirmed}
                onChange={(e) => setSpeedForm((f) => ({ ...f, authorization_confirmed: e.target.checked }))}
              />
              <span>我確認此頁面可公開測速，或我擁有分析授權。</span>
            </label>
            {speedError && <div className="insight-error">{speedError}</div>}
            <button type="submit" className="public-cta-primary" disabled={speedLoading}>
              {speedLoading ? "測速中..." : "開始測速"}
            </button>
          </form>

          <div className="insight-result-card">
            {!speedResult ? (
              <div className="insight-empty">
                <strong>會輸出哪些結果</strong>
                <span>分數、TTFB、傳輸量、阻塞 script、圖片 lazy loading、快取與壓縮建議。</span>
              </div>
            ) : (
              <>
                <div className="insight-score-row">
                  <div className={`insight-score score-${speedResult.grade}`}>
                    {speedResult.score}
                  </div>
                  <div>
                    <div className="insight-result-title">{speedResult.final_url}</div>
                    <div className="insight-result-sub">{speedResult.source}</div>
                  </div>
                </div>
                <div className="insight-metrics-grid">
                  <div><span>TTFB</span><strong>{speedResult.metrics.ttfb_ms} ms</strong></div>
                  <div><span>傳輸量</span><strong>{speedResult.metrics.transfer_kb} KB</strong></div>
                  <div><span>阻塞 script</span><strong>{speedResult.metrics.blocking_scripts}</strong></div>
                  <div><span>圖片</span><strong>{speedResult.metrics.images}</strong></div>
                </div>
                <p className="insight-note">{speedResult.core_web_vitals_note}</p>
                {speedResult.findings.length > 0 ? (
                  <ul className="insight-finding-list">
                    {speedResult.findings.map((f, idx) => (
                      <li key={`${f.title}-${idx}`}>
                        <strong>{f.title}</strong>
                        <span>{f.description}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="insight-success">未發現明顯效能風險。</div>
                )}
              </>
            )}
          </div>
        </div>
      </section>
      )}

      {tool === "phish" && (
      <section className="public-section">
        <header className="public-section-head">
          <h2>可疑網址 / 詐騙郵件檢測</h2>
          <p>貼上一個網址或一封郵件內容，本機特徵分類器幫你判斷「是否可能是釣魚／詐騙」（不外送大模型 API）</p>
        </header>
        <div className="insight-two-col">
          <form className="insight-tool-card" onSubmit={runUrlCheck}>
            <h3 className="insight-card-title">網址安全檢測（防釣魚）</h3>
            <label className="insight-field">
              <span>可疑連結</span>
              <input
                value={urlValue}
                onChange={(e) => setUrlValue(e.target.value)}
                placeholder="https://secure-login.example/verify"
                required
              />
            </label>
            {urlError && <div className="insight-error">{urlError}</div>}
            <button type="submit" className="public-cta-primary" disabled={urlLoading}>
              {urlLoading ? "分析中..." : "分析 URL"}
            </button>
            {urlResult && (
              <div className="insight-risk-result">
                <div className="insight-risk-head">
                  <strong>{urlResult.risk_score}/100</strong>
                  <RiskLevelBadge level={urlResult.risk_level} />
                </div>
                <p>{urlResult.recommendation}</p>
                <ul className="insight-feature-list">
                  {urlResult.features.slice(0, 5).map((f, idx) => (
                    <li key={`${f.title}-${idx}`}>
                      <strong>{f.title}</strong>
                      <span>{f.evidence}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </form>

          <form className="insight-tool-card" onSubmit={runEmailCheck}>
            <h3 className="insight-card-title">郵件詐騙檢測（防釣魚信）</h3>
            <label className="insight-field">
              <span>.eml / 原始信件內容</span>
              <textarea
                value={emailValue}
                onChange={(e) => setEmailValue(e.target.value)}
                placeholder={"From: notice@example.com\nAuthentication-Results: ...\n\n請立即驗證帳號..."}
                rows={9}
                required
              />
            </label>
            {emailError && <div className="insight-error">{emailError}</div>}
            <button type="submit" className="public-cta-primary" disabled={emailLoading}>
              {emailLoading ? "分析中..." : "分析郵件"}
            </button>
            {emailResult && (
              <div className="insight-risk-result">
                <div className="insight-risk-head">
                  <strong>{emailResult.risk_score}/100</strong>
                  <RiskLevelBadge level={emailResult.risk_level} />
                </div>
                <p>{emailResult.recommendation}</p>
                <div className="insight-email-meta">
                  <span>From: {emailResult.from_domain || "未解析"}</span>
                  <span>連結數: {emailResult.url_count}</span>
                </div>
                <ul className="insight-feature-list">
                  {emailResult.features.slice(0, 5).map((f, idx) => (
                    <li key={`${f.title}-${idx}`}>
                      <strong>{f.title}</strong>
                      <span>{f.evidence}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </form>
        </div>
      </section>
      )}
    </div>
  );
}

function DownloadPage() {
  const [releases, setReleases] = useState([]);
  const { canInstall, installed, trigger } = useInstallPrompt();
  useEffect(() => {
    api.get("/content/releases/").then((r) => setReleases(r.data.releases || [])).catch(() => {});
  }, []);
  const latest = releases.find((r) => r.is_latest) || releases[0];
  return (
    <div className="public-page">
      <section className="public-hero">
        <div className="public-hero-bg" aria-hidden="true">
          <span className="hero-orb hero-orb-1" />
          <span className="hero-orb hero-orb-2" />
        </div>
        <div className="public-hero-content">
          <span className="public-hero-eyebrow">DOWNLOAD · 下載安裝</span>
          <h1 className="public-hero-title">
            <span className="hero-grad">隨身</span>使用 Argus
          </h1>
          <p className="public-hero-sub">
            Argus 是 PWA（漸進式網頁應用），無需透過 App Store — 直接從瀏覽器加到主畫面，像 App 一樣開啟，支援離線瀏覽既有報告。
          </p>
          <div className="public-hero-actions">
            {installed ? (
              <span className="public-install-installed">✓ 已安裝，請從主畫面開啟</span>
            ) : (
              <button
                type="button"
                className="public-cta-primary public-install-cta"
                onClick={async () => {
                  if (canInstall) {
                    await trigger();
                  } else {
                    // 瀏覽器尚未提供安裝（如 iOS Safari 不支援程式化安裝，或事件未就緒）
                    // → 帶到各平台安裝步驟
                    document
                      .getElementById("install-guide")
                      ?.scrollIntoView({ behavior: "smooth" });
                  }
                }}
              >
                ⬇ 點擊下載
              </button>
            )}
            {!installed && latest?.download_url && (
              <a className="public-cta-ghost" href={latest.download_url}>
                取得 {latest.platform_label} 版 →
              </a>
            )}
          </div>
        </div>
      </section>

      <section className="public-section" id="install-guide">
        <header className="public-section-head">
          <h2>安裝步驟</h2>
          <p>三大平台一覽</p>
        </header>
        <div className="public-install-grid">
          <div className="public-install-card">
            <div className="public-install-icon">💻</div>
            <div className="public-install-title">桌面（Chrome / Edge）</div>
            <ol>
              <li>網址列右側點選安裝圖示 <kbd>⬇</kbd></li>
              <li>點「安裝」即出現桌面捷徑</li>
            </ol>
          </div>
          <div className="public-install-card">
            <div className="public-install-icon">🤖</div>
            <div className="public-install-title">Android（Chrome）</div>
            <ol>
              <li>右上 ⋮ 選單 → 「加到主畫面」</li>
              <li>確認 → 出現於主畫面</li>
            </ol>
          </div>
          <div className="public-install-card">
            <div className="public-install-icon">🍎</div>
            <div className="public-install-title">iOS（Safari）</div>
            <ol>
              <li>下方分享按鈕 → 「加入主畫面」</li>
              <li>確認 → 出現於主畫面</li>
            </ol>
          </div>
        </div>
      </section>

      {latest && (
        <section className="public-section">
          <header className="public-section-head">
            <h2>版本資訊</h2>
            <p>最新版 {latest.version}（{latest.platform_label}）</p>
          </header>
          <div className="public-release-card">
            <div className="public-release-version">
              <span className="public-release-badge">最新</span>
              v{latest.version}
            </div>
            <div className="public-release-date">
              {new Date(latest.released_at).toLocaleDateString("zh-Hant")}
            </div>
            <p className="public-release-notes">{latest.release_notes}</p>
            {latest.download_url && (
              <a className="public-cta-primary" href={latest.download_url}>
                ⬇ 取得 {latest.platform_label}
              </a>
            )}
          </div>

          {releases.length > 1 && (
            <details className="public-release-history">
              <summary>查看歷史版本</summary>
              <ul>
                {releases.slice(1).map((r) => (
                  <li key={r.id}>
                    <strong>v{r.version}</strong>
                    <span className="public-release-history-date">
                      {new Date(r.released_at).toLocaleDateString("zh-Hant")}
                    </span>
                    <span>{r.release_notes}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </section>
      )}
    </div>
  );
}

// ============================================================
// /admin React 後台（精簡 5 大分類 + dark cyan 主題）
// 走獨立 layout，不顯示前台 TopNav；只有 is_staff 可進入。
// ============================================================

const ADMIN_NAV_ITEMS = [
  { to: "/admin/overview", label: "概覽", emoji: "📊" },
  { to: "/admin/users", label: "使用者", emoji: "👥" },
  { to: "/admin/scans", label: "掃描", emoji: "🔍" },
  { to: "/admin/transactions", label: "交易", emoji: "💳" },
  { to: "/admin/plans", label: "方案", emoji: "💼" },
  { to: "/admin/content", label: "內容", emoji: "📝" },
  { to: "/admin/reviews", label: "評論", emoji: "⭐" },
  { to: "/admin/settings", label: "設定", emoji: "⚙️" },
];

function RequireAdmin({ children }) {
  const accessToken = useArgusStore((s) => s.accessToken);
  const me = useArgusStore((s) => s.me);
  const fetchMe = useArgusStore((s) => s.fetchMe);
  useEffect(() => {
    if (accessToken && me === null) fetchMe();
  }, [accessToken, me, fetchMe]);
  if (!accessToken) {
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  if (me === null) {
    return <div className="admin-loading">驗證權限中…</div>;
  }
  if (!me.is_staff) {
    return (
      <div className="admin-forbidden">
        <h2>沒有後台權限</h2>
        <p>此帳號（{me.username}）不是管理員。如需後台存取，請聯絡 superuser。</p>
        <NavLink className="primary-button mt-3 inline-block" to="/dashboard">
          回到 Dashboard
        </NavLink>
      </div>
    );
  }
  return children;
}

function AdminLayout() {
  const { setToken, me, replayIntro } = useArgusStore();
  const navigate = useNavigate();
  function handleLogout() {
    setToken(null);
    navigate("/login");
  }
  // 超級管理員額外看到「📜 操作紀錄」分頁
  const navItems = me?.is_superuser
    ? [...ADMIN_NAV_ITEMS, { to: "/admin/audit-log", label: "操作日誌", emoji: "📜" }, { to: "/admin/announcements", label: "公告管理", emoji: "📢" }]
    : ADMIN_NAV_ITEMS;
  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <button type="button" className="admin-brand" onClick={replayIntro} title="回到前台首頁" aria-label="回到前台首頁">
          <img src={brandLogo} className="admin-brand-logo" alt="ARGUS" />
          <span className="admin-brand-sub">管理後台</span>
        </button>
        <nav className="admin-nav">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `admin-nav-link ${isActive ? "active" : ""}`
              }
            >
              <span className="admin-nav-emoji" aria-hidden="true">{item.emoji}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="admin-sidebar-footer">
          <NavLink to="/dashboard" className="admin-side-link">
            ← 回前台
          </NavLink>
          <button
            type="button"
            className="admin-side-link"
            onClick={handleLogout}
          >
            登出
          </button>
        </div>
      </aside>
      <main className="admin-main">
        <Outlet />
      </main>
    </div>
  );
}

function AdminStatCard({ label, value, hint, tone = "cyan" }) {
  return (
    <div className={`admin-stat-card tone-${tone}`}>
      <div className="admin-stat-label">{label}</div>
      <div className="admin-stat-value">{value}</div>
      {hint && <div className="admin-stat-hint">{hint}</div>}
    </div>
  );
}

function AdminMiniChart({ series, keys, height = 110 }) {
  // series: [{date, ...values}]；keys: [{key, label, color}]
  if (!series || series.length === 0) {
    return <div className="admin-empty">尚無資料</div>;
  }
  const w = 480;
  const padding = { top: 8, right: 8, bottom: 24, left: 36 };
  const plotW = w - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;
  const allValues = series.flatMap((row) => keys.map((k) => row[k.key] || 0));
  const maxV = Math.max(...allValues, 1);
  const step = series.length > 1 ? plotW / (series.length - 1) : 0;
  const yFor = (v) => padding.top + plotH - (v / maxV) * plotH;
  const xFor = (i) => padding.left + i * step;
  const yTicks = [0, Math.round(maxV / 2), maxV];

  return (
    <svg className="admin-mini-chart" viewBox={`0 0 ${w} ${height}`} width="100%" height={height}>
      {yTicks.map((t) => (
        <g key={t}>
          <line
            x1={padding.left}
            x2={w - padding.right}
            y1={yFor(t)}
            y2={yFor(t)}
            stroke="#e2e8f0"
            strokeDasharray="2 4"
          />
          <text x={padding.left - 6} y={yFor(t) + 3} fontSize="10" fill="#94a3b8" textAnchor="end">
            {t.toLocaleString()}
          </text>
        </g>
      ))}
      {keys.map((k) => {
        const points = series
          .map((row, i) => `${xFor(i)},${yFor(row[k.key] || 0)}`)
          .join(" ");
        return (
          <polyline
            key={k.key}
            points={points}
            fill="none"
            stroke={k.color}
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        );
      })}
      {series.length > 0 && (
        <>
          <text x={xFor(0)} y={height - 4} fontSize="10" fill="#94a3b8" textAnchor="start">
            {series[0].date.slice(5)}
          </text>
          <text x={xFor(series.length - 1)} y={height - 4} fontSize="10" fill="#94a3b8" textAnchor="end">
            {series[series.length - 1].date.slice(5)}
          </text>
        </>
      )}
    </svg>
  );
}

function AdminOverviewPage() {
  const [data, setData] = useState(null);
  const [dash, setDash] = useState(null);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([api.get("/admin/overview/"), api.get("/admin/dashboard/")])
      .then(([o, d]) => { setData(o.data); setDash(d.data); })
      .catch(() => setError("無法載入概覽。"));
  }, []);

  if (error) return <div className="admin-error">{error}</div>;
  if (!data || !dash) return <div className="admin-loading">載入中…</div>;
  const t = data.totals;
  const providerMaxTokens = Math.max(
    ...(dash.provider_breakdown || []).map((r) => r.tokens), 1,
  );

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1>概覽</h1>
        <p>系統整體狀態與最近 14 天活動</p>
      </header>

      <div className="admin-stat-grid">
        <AdminStatCard
          label="使用者總數"
          value={t.users.toLocaleString()}
          hint={`錢包 ${t.wallets.toLocaleString()} 個`}
          tone="cyan"
        />
        <AdminStatCard
          label="累計營收"
          value={`NT$ ${t.revenue_ntd.toLocaleString()}`}
          hint={`流通 coin ${t.coin_balance_total.toLocaleString()}`}
          tone="violet"
        />
        <AdminStatCard
          label="訂單"
          value={t.orders.toLocaleString()}
          hint={`本月 ${t.orders_this_month} / 已付 ${t.orders_paid}`}
          tone="good"
        />
        <AdminStatCard
          label="掃描總數"
          value={t.scans.toLocaleString()}
          hint={`本月 ${t.scans_this_month.toLocaleString()}`}
          tone="amber"
        />
        <AdminStatCard
          label="AI Token 用量"
          value={t.ai_tokens_total.toLocaleString()}
          hint={`本月 ${t.ai_tokens_this_month.toLocaleString()} / Sessions ${t.ai_sessions_total}`}
          tone="violet"
        />
        <AdminStatCard
          label="評論"
          value={`${t.avg_rating ?? "—"} ★`}
          hint={`共 ${t.reviews} 則 / 待回覆 ${t.reviews_pending}`}
          tone={t.reviews_pending > 0 ? "rose" : "good"}
        />
      </div>

      {/* 14 天時序圖：3 條線（訂單、AI tokens、掃描） */}
      <section className="admin-panel">
        <div className="admin-panel-head-row">
          <h3>最近 14 天活動</h3>
          <div className="admin-chart-legend">
            <span><i style={{ background: "#06b6d4" }} />AI tokens</span>
            <span><i style={{ background: "#6366f1" }} />訂單金額</span>
            <span><i style={{ background: "#f59e0b" }} />掃描數</span>
          </div>
        </div>
        <AdminMiniChart
          series={dash.series}
          keys={[
            { key: "ai_tokens", color: "#06b6d4" },
            { key: "revenue_ntd", color: "#6366f1" },
            { key: "scans", color: "#f59e0b" },
          ]}
          height={140}
        />
      </section>

      <div className="admin-grid-2col">
        <section className="admin-panel">
          <h3>AI Provider 用量分佈</h3>
          {dash.provider_breakdown.length === 0 ? (
            <p className="admin-empty">尚無 AI 使用紀錄</p>
          ) : (
            <div className="admin-provider-bars">
              {dash.provider_breakdown.map((row) => (
                <div className="admin-provider-row" key={`${row.provider}-${row.model}`}>
                  <div className="admin-provider-meta">
                    <span className="admin-provider-name">{row.provider}</span>
                    <span className="admin-provider-model">{row.model || "—"}</span>
                  </div>
                  <div className="admin-provider-track">
                    <div
                      className="admin-provider-fill"
                      style={{ width: `${(row.tokens / providerMaxTokens) * 100}%` }}
                    />
                  </div>
                  <div className="admin-provider-stats">
                    <span className="admin-provider-tokens">{row.tokens.toLocaleString()}</span>
                    <span className="admin-provider-sessions">{row.sessions} sess</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="admin-panel">
          <h3>Top 10 AI 用戶</h3>
          {dash.top_ai_users.length === 0 ? (
            <p className="admin-empty">尚無 AI 使用紀錄</p>
          ) : (
            <table className="admin-table compact">
              <thead><tr><th>使用者</th><th className="num">tokens</th><th className="num">sessions</th></tr></thead>
              <tbody>
                {dash.top_ai_users.map((u) => (
                  <tr key={u.id} className="clickable" onClick={() => navigate(`/admin/users/${u.id}`)}>
                    <td>
                      <div className="admin-cell-primary">{u.username}</div>
                      <div className="admin-cell-secondary">{u.email}</div>
                    </td>
                    <td className="num"><span className="admin-coin">{u.ai_tokens.toLocaleString()}</span></td>
                    <td className="num">{u.ai_sessions}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>

      <div className="admin-grid-2col">
        <section className="admin-panel">
          <h3>最近購買</h3>
          {data.recent_purchases.length === 0 ? (
            <p className="admin-empty">尚無購買紀錄</p>
          ) : (
            <table className="admin-table compact">
              <thead><tr><th>時間</th><th>方案</th><th className="num">金額</th></tr></thead>
              <tbody>
                {data.recent_purchases.map((tx) => (
                  <tr key={tx.id}>
                    <td>{new Date(tx.created_at).toLocaleString("zh-Hant")}</td>
                    <td>{tx.plan_name || "—"}</td>
                    <td className="num">+{tx.amount} coin</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </div>
  );
}

function AdminPagination({ page, totalPages, onChange }) {
  if (totalPages <= 1) return null;
  return (
    <div className="admin-pagination">
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
      >← 上一頁</button>
      <span>{page} / {totalPages}</span>
      <button
        type="button"
        disabled={page >= totalPages}
        onClick={() => onChange(page + 1)}
      >下一頁 →</button>
    </div>
  );
}

function AdminUsersPage() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  async function load() {
    const response = await api.get("/admin/users/", {
      params: { q: search, page },
    });
    setData(response.data);
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [page]);

  function handleSearchSubmit(e) {
    e.preventDefault();
    setPage(1);
    load();
  }

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1>使用者</h1>
        <p>所有註冊帳號與其點數狀態</p>
      </header>

      <form className="admin-search-bar" onSubmit={handleSearchSubmit}>
        <input
          className="admin-input"
          placeholder="搜尋 email、姓名或帳號"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <button className="admin-btn" type="submit">搜尋</button>
      </form>

      {!data && <div className="admin-loading">載入中…</div>}
      {data && (
        <>
          <table className="admin-table">
            <thead>
              <tr>
                <th>使用者</th>
                <th>email</th>
                <th className="num">餘額</th>
                <th className="num">累積購買</th>
                <th className="num">掃描數</th>
                <th>最近登入</th>
              </tr>
            </thead>
            <tbody>
              {data.users.map((u) => (
                <tr
                  key={u.id}
                  className="clickable"
                  onClick={() => navigate(`/admin/users/${u.id}`)}
                >
                  <td>
                    <div className="admin-cell-primary">{u.full_name}</div>
                    <div className="admin-cell-secondary">@{u.username} {u.is_staff && <span className="admin-staff-chip">staff</span>}</div>
                  </td>
                  <td>{u.email}</td>
                  <td className="num"><span className="admin-coin">{u.balance.toLocaleString()}</span></td>
                  <td className="num">{u.total_purchased_ntd > 0 ? `NT$ ${u.total_purchased_ntd.toLocaleString()}` : "—"}</td>
                  <td className="num">{u.total_scans_used}</td>
                  <td>{u.last_login ? new Date(u.last_login).toLocaleString("zh-Hant") : "從未"}</td>
                </tr>
              ))}
              {data.users.length === 0 && (
                <tr><td colSpan="6" className="admin-empty">沒有符合的使用者</td></tr>
              )}
            </tbody>
          </table>
          <AdminPagination page={data.page} totalPages={data.total_pages} onChange={setPage} />
        </>
      )}
    </div>
  );
}

function AdminUserDetailPage() {
  const { userId } = useParams();
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [error, setError] = useState("");
  const [delta, setDelta] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState(null);

  async function load() {
    try {
      const response = await api.get(`/admin/users/${userId}/`);
      setUser(response.data);
    } catch {
      setError("找不到此使用者");
    }
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [userId]);

  async function handleAdjust(e) {
    e.preventDefault();
    const value = parseInt(delta, 10);
    if (!value) {
      setFeedback({ tone: "bad", message: "請輸入非 0 的整數" });
      return;
    }
    setBusy(true);
    setFeedback(null);
    try {
      const response = await api.post(`/admin/users/${userId}/adjust-coin/`, {
        delta: value,
        note: note || "管理員手動調整",
      });
      setFeedback({
        tone: "good",
        message: `已${value > 0 ? "補" : "扣"} ${Math.abs(response.data.transaction.amount)} coin，當前餘額 ${response.data.wallet_balance}`,
      });
      setDelta("");
      setNote("");
      await load();
    } catch (err) {
      setFeedback({ tone: "bad", message: err?.response?.data?.detail || "調整失敗" });
    } finally {
      setBusy(false);
    }
  }

  if (error) return <div className="admin-error">{error}</div>;
  if (!user) return <div className="admin-loading">載入中…</div>;
  const w = user.wallet;

  return (
    <div className="admin-page">
      <button
        type="button"
        className="admin-back-link"
        onClick={() => navigate("/admin/users")}
      >← 回使用者列表</button>

      <header className="admin-page-head">
        <h1>{user.full_name}</h1>
        <p>@{user.username} · {user.email}</p>
      </header>

      <div className="admin-grid-2col">
        <section className="admin-panel">
          <h3>基本資料</h3>
          <dl className="admin-dl">
            <dt>狀態</dt><dd>{user.is_active ? "啟用" : "停用"} {user.is_staff && <span className="admin-staff-chip">staff</span>} {user.is_superuser && <span className="admin-super-chip">superuser</span>}</dd>
            <dt>註冊時間</dt><dd>{new Date(user.date_joined).toLocaleString("zh-Hant")}</dd>
            <dt>最後登入</dt><dd>{user.last_login ? new Date(user.last_login).toLocaleString("zh-Hant") : "從未"}</dd>
          </dl>
        </section>

        <section className="admin-panel">
          <h3>點數錢包</h3>
          {w ? (
            <>
              <div className="admin-balance-big">
                {w.balance.toLocaleString()}<span> coin</span>
              </div>
              <dl className="admin-dl">
                <dt>累積購買</dt><dd>NT$ {w.total_purchased_ntd.toLocaleString()}</dd>
                <dt>累積掃描</dt><dd>{w.total_scans_used} 次</dd>
                <dt>最近月贈點</dt><dd>{w.last_bonus_year ? `${w.last_bonus_year}-${String(w.last_bonus_month).padStart(2,"0")}` : "—"}</dd>
              </dl>
            </>
          ) : <p className="admin-empty">尚未建立錢包</p>}
        </section>
      </div>

      <section className="admin-panel">
        <h3>調整點數</h3>
        <form className="admin-adjust-form" onSubmit={handleAdjust}>
          <div className="admin-adjust-row">
            <input
              className="admin-input"
              type="number"
              placeholder="變動金額（正=補、負=扣）"
              value={delta}
              onChange={(e) => setDelta(e.target.value)}
            />
            <input
              className="admin-input wide"
              placeholder="備註（將寫入交易紀錄）"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <button className="admin-btn primary" type="submit" disabled={busy}>
              {busy ? "處理中…" : "送出"}
            </button>
          </div>
          <div className="admin-quick-row">
            {[100, 500, 1000, -100, -500].map((v) => (
              <button key={v} type="button" className="admin-quick-btn" onClick={() => setDelta(String(v))}>
                {v > 0 ? `+${v}` : v}
              </button>
            ))}
          </div>
          {feedback && (
            <div className={`admin-feedback tone-${feedback.tone}`}>{feedback.message}</div>
          )}
        </form>
      </section>

      {user.ai_usage && (
        <section className="admin-panel">
          <h3>AI 使用量</h3>
          <div className="admin-ai-summary">
            <div>
              <div className="admin-stat-label">總 Tokens</div>
              <div className="admin-balance-big" style={{ marginBottom: 0 }}>
                {user.ai_usage.total_tokens.toLocaleString()}
              </div>
            </div>
            <div>
              <div className="admin-stat-label">Sessions</div>
              <div className="admin-balance-big" style={{ marginBottom: 0 }}>
                {user.ai_usage.total_sessions}
              </div>
            </div>
          </div>
          {user.ai_usage.by_provider.length > 0 && (
            <table className="admin-table compact" style={{ marginTop: 12 }}>
              <thead><tr><th>Provider</th><th>Model</th><th className="num">Sessions</th><th className="num">Tokens</th></tr></thead>
              <tbody>
                {user.ai_usage.by_provider.map((row, i) => (
                  <tr key={`${row.provider}-${row.model}-${i}`}>
                    <td>{row.provider}</td>
                    <td>{row.model || "—"}</td>
                    <td className="num">{row.sessions}</td>
                    <td className="num"><span className="admin-coin">{row.tokens.toLocaleString()}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      <section className="admin-panel">
        <h3>最近 30 筆交易</h3>
        <table className="admin-table compact">
          <thead>
            <tr><th>時間</th><th>類型</th><th className="num">變動</th><th className="num">餘額</th><th>備註</th></tr>
          </thead>
          <tbody>
            {user.recent_transactions.map((tx) => (
              <tr key={tx.id}>
                <td>{new Date(tx.created_at).toLocaleString("zh-Hant")}</td>
                <td>{tx.kind_label}</td>
                <td className={`num ${tx.amount > 0 ? "tx-pos" : "tx-neg"}`}>{tx.amount > 0 ? "+" : ""}{tx.amount}</td>
                <td className="num">{tx.balance_after}</td>
                <td className="admin-cell-secondary">{tx.note}</td>
              </tr>
            ))}
            {user.recent_transactions.length === 0 && (
              <tr><td colSpan="5" className="admin-empty">尚無交易紀錄</td></tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function AdminTransactionsPage({ embedded }) {
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [kind, setKind] = useState("");

  async function load() {
    const response = await api.get("/admin/transactions/", {
      params: { page, kind: kind || undefined },
    });
    setData(response.data);
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [page, kind]);

  const KIND_OPTIONS = [
    { v: "", label: "全部類型" },
    { v: "monthly_bonus", label: "每月贈點" },
    { v: "purchase", label: "購買" },
    { v: "scan_hold", label: "掃描預扣" },
    { v: "scan_refund", label: "掃描退款" },
    { v: "admin_adjust", label: "管理員調整" },
  ];

  const content = (
    <>
      {!embedded && (
        <header className="admin-page-head">
          <h1>交易紀錄</h1>
          <p>所有 coin 異動的審計紀錄</p>
        </header>
      )}

      <div className="admin-filter-bar">
        <select
          className="admin-input"
          value={kind}
          onChange={(e) => { setKind(e.target.value); setPage(1); }}
        >
          {KIND_OPTIONS.map((o) => (
            <option key={o.v} value={o.v}>{o.label}</option>
          ))}
        </select>
      </div>

      {!data && <div className="admin-loading">載入中…</div>}
      {data && (
        <>
          <table className="admin-table">
            <thead>
              <tr>
                <th>時間</th><th>使用者</th><th>類型</th>
                <th className="num">變動</th><th className="num">餘額</th>
                <th>來源</th><th>備註</th>
              </tr>
            </thead>
            <tbody>
              {data.transactions.map((tx) => (
                <tr key={tx.id}>
                  <td>{new Date(tx.created_at).toLocaleString("zh-Hant")}</td>
                  <td>{tx.scan_origin || (tx.plan_name ? `購買 ${tx.plan_name}` : "—")}</td>
                  <td>{tx.kind_label}</td>
                  <td className={`num ${tx.amount > 0 ? "tx-pos" : "tx-neg"}`}>{tx.amount > 0 ? "+" : ""}{tx.amount}</td>
                  <td className="num">{tx.balance_after}</td>
                  <td>{tx.admin_actor_username ? `admin: ${tx.admin_actor_username}` : (tx.plan_name || tx.scan_origin || "—")}</td>
                  <td className="admin-cell-secondary">{tx.note}</td>
                </tr>
              ))}
              {data.transactions.length === 0 && (
                <tr><td colSpan="7" className="admin-empty">沒有符合的交易</td></tr>
              )}
            </tbody>
          </table>
          <AdminPagination page={data.page} totalPages={data.total_pages} onChange={setPage} />
        </>
      )}
    </>
  );

  if (embedded) return content;
  return <div className="admin-page">{content}</div>;
}

function AdminReviewsPage() {
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [onlyPending, setOnlyPending] = useState(false);
  const [draftReplies, setDraftReplies] = useState({});

  async function load() {
    const response = await api.get("/admin/reviews/", {
      params: { page, pending: onlyPending ? "1" : undefined },
    });
    setData(response.data);
    // 初始化每則的回覆草稿
    const initial = {};
    for (const r of response.data.reviews) {
      initial[r.id] = r.admin_reply || "";
    }
    setDraftReplies(initial);
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [page, onlyPending]);

  async function handleReply(reviewId) {
    try {
      await api.post(`/admin/reviews/${reviewId}/reply/`, {
        reply: draftReplies[reviewId] || "",
      });
      await load();
    } catch {
      alert("回覆失敗");
    }
  }

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1>評論</h1>
        <p>{data ? `共 ${data.total} 則，待回覆 ${data.pending_count}` : "載入中…"}</p>
      </header>

      {data && (
        <div className="admin-stat-grid" style={{ gridTemplateColumns: "repeat(3,1fr)" }}>
          <AdminStatCard label="總評論數" value={data.total} tone="cyan" />
          <AdminStatCard label="平均評分" value={data.avg_rating ? `${data.avg_rating} ★` : "—"} tone="green" />
          <AdminStatCard label="待回覆" value={data.pending_count} tone={data.pending_count > 0 ? "yellow" : "good"} />
        </div>
      )}

      <div className="admin-filter-bar">
        <label className="admin-checkbox">
          <input
            type="checkbox"
            checked={onlyPending}
            onChange={(e) => { setOnlyPending(e.target.checked); setPage(1); }}
          />
          只看待回覆
        </label>
      </div>

      {data && data.reviews.map((review) => (
        <article key={review.id} className={`admin-review ${review.is_pending ? "is-pending" : ""}`}>
          <header className="admin-review-head">
            <div>
              <div className="admin-review-user">
                {review.full_name}
                <span className="admin-cell-secondary"> @{review.username}</span>
              </div>
              <div className="admin-review-time">
                {new Date(review.created_at).toLocaleString("zh-Hant")}
              </div>
            </div>
            <div className="admin-review-rating">
              {"★".repeat(review.rating)}{"☆".repeat(5 - review.rating)}
              <span className="admin-cell-secondary"> ({review.rating})</span>
            </div>
          </header>
          {review.comment && (
            <p className="admin-review-body">{review.comment}</p>
          )}
          <div className="admin-review-reply-section">
            <textarea
              className="admin-input admin-reply-input"
              placeholder="回覆使用者…（清空則移除回覆）"
              rows={2}
              value={draftReplies[review.id] ?? ""}
              onChange={(e) => setDraftReplies({ ...draftReplies, [review.id]: e.target.value })}
            />
            <button
              type="button"
              className="admin-btn primary"
              onClick={() => handleReply(review.id)}
            >
              {review.admin_reply ? "更新回覆" : "送出回覆"}
            </button>
          </div>
          {review.admin_reply && (
            <div className="admin-review-existing-reply">
              ✓ 已回覆 ({review.admin_replied_at ? new Date(review.admin_replied_at).toLocaleString("zh-Hant") : ""})
              {review.admin_replied_by_username ? ` by ${review.admin_replied_by_username}` : ""}
            </div>
          )}
        </article>
      ))}
      {data && data.reviews.length === 0 && (
        <div className="admin-empty admin-panel">沒有符合的評論</div>
      )}
      {data && <AdminPagination page={data.page} totalPages={data.total_pages} onChange={setPage} />}
    </div>
  );
}

function AdminScansPage({ embedded }) {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);

  async function load() {
    const response = await api.get("/admin/scans/", {
      params: { q: search, status: statusFilter || undefined, page },
    });
    setData(response.data);
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [page, statusFilter]);

  function handleSearchSubmit(e) {
    e.preventDefault();
    setPage(1);
    load();
  }

  const content = (
    <>
      {!embedded && (
        <header className="admin-page-head">
          <h1>掃描</h1>
          <p>所有使用者的掃描任務</p>
        </header>
      )}

      <form className="admin-search-bar" onSubmit={handleSearchSubmit}>
        <input
          className="admin-input"
          placeholder="搜尋網址或使用者"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="admin-input"
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
        >
          <option value="">全部狀態</option>
          {Object.entries(STATUS_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v.label}</option>
          ))}
        </select>
        <button className="admin-btn" type="submit">搜尋</button>
      </form>

      {!data && <div className="admin-loading">載入中…</div>}
      {data && (
        <>
          <table className="admin-table">
            <thead>
              <tr>
                <th>時間</th><th>使用者</th><th>網址</th>
                <th>狀態</th><th>模式</th>
                <th className="num">分數</th><th className="num">頁數</th><th className="num">問題</th>
                <th className="num">耗時</th>
              </tr>
            </thead>
            <tbody>
              {data.scans.map((s) => (
                <tr key={s.id} className="clickable" onClick={() => navigate(`/admin/scans/${s.id}`)}>
                  <td>{new Date(s.created_at).toLocaleString("zh-Hant")}</td>
                  <td>{s.username}</td>
                  <td className="truncate" title={s.origin}>{s.origin}</td>
                  <td><span className={`admin-status ${s.status}`}>{STATUS_LABELS[s.status]?.label || s.status}</span></td>
                  <td>{s.scan_mode === "active" ? "主動" : "被動"}</td>
                  <td className="num">{s.overall_score ?? "—"}</td>
                  <td className="num">{s.pages_count}</td>
                  <td className="num">{s.findings_count}</td>
                  <td className="num">{s.duration_sec ? `${s.duration_sec}s` : "—"}</td>
                </tr>
              ))}
              {data.scans.length === 0 && (
                <tr><td colSpan="9" className="admin-empty">沒有符合的掃描</td></tr>
              )}
            </tbody>
          </table>
          <AdminPagination page={data.page} totalPages={data.total_pages} onChange={setPage} />
        </>
      )}
    </>
  );

  if (embedded) return content;
  return <div className="admin-page">{content}</div>;
}

function AdminScanDetailPage() {
  const { scanId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get(`/admin/scans/${scanId}/`)
      .then((r) => setData(r.data))
      .catch(() => setError("找不到此掃描"));
  }, [scanId]);

  if (error) return <div className="admin-error">{error}</div>;
  if (!data) return <div className="admin-loading">載入中…</div>;
  const s = data.scan;

  return (
    <div className="admin-page">
      <button type="button" className="admin-back-link" onClick={() => navigate("/admin/scans")}>← 回掃描列表</button>
      <header className="admin-page-head">
        <h1>掃描 #{s.id}</h1>
        <p>{s.origin} · {s.username}</p>
      </header>

      <div className="admin-grid-2col">
        <section className="admin-panel">
          <h3>狀態</h3>
          <dl className="admin-dl">
            <dt>狀態</dt><dd><span className={`admin-status ${s.status}`}>{STATUS_LABELS[s.status]?.label || s.status}</span></dd>
            <dt>模式</dt><dd>{s.scan_mode === "active" ? "主動測試" : "被動偵測"}</dd>
            <dt>建立時間</dt><dd>{new Date(s.created_at).toLocaleString("zh-Hant")}</dd>
            <dt>完成時間</dt><dd>{s.completed_at ? new Date(s.completed_at).toLocaleString("zh-Hant") : "—"}</dd>
            <dt>耗時</dt><dd>{s.duration_sec ? `${s.duration_sec} 秒` : "—"}</dd>
          </dl>
        </section>

        <section className="admin-panel">
          <h3>結果摘要</h3>
          <dl className="admin-dl">
            <dt>總分</dt><dd>{s.overall_score ?? "—"}</dd>
            <dt>頁數</dt><dd>{s.pages_count}</dd>
            <dt>問題數</dt><dd>{s.findings_count}</dd>
            <dt>最大頁數設定</dt><dd>{s.max_pages}</dd>
          </dl>
        </section>
      </div>

      {data.category_scores && Object.keys(data.category_scores).length > 0 && (
        <section className="admin-panel">
          <h3>各類別分數</h3>
          <div className="admin-cat-scores">
            {Object.entries(data.category_scores).map(([cat, score]) => (
              <div key={cat} className="admin-cat-score-item">
                <div className="admin-cat-score-label">{cat.toUpperCase()}</div>
                <div className="admin-cat-score-value">{Math.round(score)}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {data.error_message && (
        <section className="admin-panel admin-panel-danger">
          <h3>錯誤訊息</h3>
          <pre className="admin-error-pre">{data.error_message}</pre>
        </section>
      )}

      <div className="admin-link-row">
        <NavLink to={`/scans/${s.id}`} className="admin-btn">
          以使用者視角查看詳情報告 →
        </NavLink>
      </div>
    </div>
  );
}

// ------ AdminContentPage：內容速覽（編輯走 Jazzmin Django Admin） ------

// ------ 通用 CMS CRUD 元件 ------
function AdminCmsManager({ schema }) {
  const [items, setItems] = useState([]);
  const [editing, setEditing] = useState(null); // null 或 item or "new"
  const [draft, setDraft] = useState({});
  const [feedback, setFeedback] = useState(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    const r = await api.get(schema.endpoint);
    setItems(r.data.items || []);
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [schema.endpoint]);

  function startNew() {
    const blank = {};
    for (const f of schema.fields) {
      blank[f.key] = f.default !== undefined ? f.default :
        (f.type === "boolean" ? false :
        (f.type === "number" ? 0 :
        (f.type === "json" ? [] : "")));
    }
    setDraft(blank);
    setEditing("new");
    setFeedback(null);
  }

  function startEdit(item) {
    setDraft({ ...item });
    setEditing(item);
    setFeedback(null);
  }

  function cancel() {
    setEditing(null);
    setDraft({});
    setFeedback(null);
  }

  async function save(e) {
    e?.preventDefault();
    setBusy(true);
    setFeedback(null);
    try {
      // 處理 JSON 欄位（skills 等存 array）
      const payload = { ...draft };
      for (const f of schema.fields) {
        if (f.type === "json" && typeof payload[f.key] === "string") {
          payload[f.key] = payload[f.key]
            .split(/[,，\s]+/).map((s) => s.trim()).filter(Boolean);
        }
      }
      if (editing === "new") {
        await api.post(schema.endpoint, payload);
      } else {
        await api.put(`${schema.endpoint}${editing.id}/`, payload);
      }
      setFeedback({ tone: "good", message: "已儲存" });
      await load();
      setTimeout(() => cancel(), 600);
    } catch (err) {
      const data = err?.response?.data;
      const msg = data
        ? Object.entries(data).map(([k, v]) =>
            `${k}：${Array.isArray(v) ? v.join(",") : v}`).join("；")
        : "儲存失敗";
      setFeedback({ tone: "bad", message: msg });
    } finally {
      setBusy(false);
    }
  }

  async function remove(item) {
    if (!window.confirm(`確定刪除「${item[schema.titleField || "name"] || "#" + item.id}」？`)) return;
    await api.delete(`${schema.endpoint}${item.id}/`);
    await load();
  }

  return (
    <section className="admin-panel">
      <div className="admin-panel-head-row">
        <h3>{schema.title}（{items.length}）</h3>
        <div className="admin-panel-head-actions">
          {schema.previewPath && (
            <a
              className="admin-btn"
              href={schema.previewPath}
              target="_blank"
              rel="noreferrer noopener"
              title="另開新分頁預覽前台效果"
            >
              {schema.previewLabel || "預覽前台 ↗"}
            </a>
          )}
          <button type="button" className="admin-btn primary" onClick={startNew}>
            + 新增
          </button>
        </div>
      </div>

      {/* 列表 */}
      <table className="admin-table">
        <thead>
          <tr>
            {schema.displayFields.map((f) => (
              <th key={f.key} className={f.num ? "num" : ""}>{f.label}</th>
            ))}
            <th style={{ width: 120 }}>操作</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              {schema.displayFields.map((f) => (
                <td key={f.key} className={f.num ? "num" : ""}>
                  {f.render ? f.render(item) : (item[f.key] ?? "—")}
                </td>
              ))}
              <td>
                <button type="button" className="admin-btn" onClick={() => startEdit(item)}
                  style={{ padding: "4px 10px", fontSize: 12, marginRight: 4 }}>編輯</button>
                <button type="button" className="admin-btn" onClick={() => remove(item)}
                  style={{ padding: "4px 10px", fontSize: 12, color: "#dc2626", borderColor: "#fecaca" }}>刪</button>
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr><td colSpan={schema.displayFields.length + 1} className="admin-empty">
              尚無資料，點上方「+ 新增」開始
            </td></tr>
          )}
        </tbody>
      </table>

      {/* 編輯 form modal */}
      {editing && (
        <div className="admin-modal-backdrop" onClick={cancel}>
          <form className="admin-modal" onClick={(e) => e.stopPropagation()} onSubmit={save}>
            <div className="admin-modal-head">
              <h4>{editing === "new" ? `新增${schema.title}` : `編輯 #${editing.id}`}</h4>
              <button type="button" className="admin-modal-close" onClick={cancel}>×</button>
            </div>
            <div className="admin-modal-body">
              {schema.fields.map((f) => (
                <div key={f.key} className="wizard-field">
                  <label htmlFor={`cms-${f.key}`}>
                    {f.label}{f.required && " *"}
                    {f.hint && <span className="wizard-field-hint">{f.hint}</span>}
                  </label>
                  {f.type === "textarea" ? (
                    <textarea
                      id={`cms-${f.key}`}
                      className="admin-input"
                      rows={f.rows || 3}
                      value={draft[f.key] ?? ""}
                      onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })}
                    />
                  ) : f.type === "boolean" ? (
                    <label className="admin-checkbox">
                      <input
                        type="checkbox"
                        checked={!!draft[f.key]}
                        onChange={(e) => setDraft({ ...draft, [f.key]: e.target.checked })}
                      /> 啟用
                    </label>
                  ) : f.type === "select" ? (
                    <select
                      id={`cms-${f.key}`}
                      className="admin-input"
                      value={draft[f.key] ?? ""}
                      onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })}
                    >
                      {f.options.map((o) => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  ) : f.type === "json" ? (
                    <input
                      id={`cms-${f.key}`}
                      className="admin-input"
                      placeholder="用逗號分隔，例：React,Django,Figma"
                      value={Array.isArray(draft[f.key]) ? draft[f.key].join(", ") : (draft[f.key] || "")}
                      onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })}
                    />
                  ) : (
                    <input
                      id={`cms-${f.key}`}
                      className="admin-input"
                      type={f.type === "number" ? "number" : (f.type === "datetime" ? "datetime-local" : "text")}
                      value={draft[f.key] ?? ""}
                      onChange={(e) => setDraft({ ...draft, [f.key]:
                        f.type === "number" ? Number(e.target.value) : e.target.value })}
                    />
                  )}
                </div>
              ))}
              {feedback && (
                <div className={`admin-feedback tone-${feedback.tone}`}>{feedback.message}</div>
              )}
            </div>
            <div className="admin-modal-foot">
              <button type="button" className="admin-btn" onClick={cancel}>取消</button>
              <button type="submit" className="admin-btn primary" disabled={busy}>
                {busy ? "儲存中…" : "儲存"}
              </button>
            </div>
          </form>
        </div>
      )}
    </section>
  );
}

const FEATURE_SCHEMA = {
  endpoint: "/admin/cms/features/",
  title: "專案特色卡片",
  previewPath: "/project",
  previewLabel: "預覽 /project",
  titleField: "title",
  fields: [
    { key: "title", label: "標題", type: "text", required: true },
    { key: "icon", label: "圖示 emoji", type: "text", hint: "例：🕷️ 🔍 🤖" },
    { key: "description", label: "說明", type: "textarea", rows: 3, required: true },
    { key: "sort_order", label: "排序", type: "number", default: 0 },
    { key: "is_active", label: "啟用", type: "boolean", default: true },
  ],
  displayFields: [
    { key: "sort_order", label: "順序", num: true },
    { key: "icon", label: "圖示", render: (i) => <span style={{ fontSize: 22 }}>{i.icon}</span> },
    { key: "title", label: "標題" },
    { key: "is_active", label: "啟用", render: (i) => i.is_active ? "✓" : "—" },
  ],
};

const TEAM_SCHEMA = {
  endpoint: "/admin/cms/team/",
  title: "團隊成員",
  previewPath: "/team",
  previewLabel: "預覽 /team",
  titleField: "name",
  fields: [
    { key: "name", label: "姓名", type: "text", required: true },
    { key: "student_id", label: "學號", type: "text", hint: "例：11246034" },
    { key: "role", label: "角色", type: "text", required: true },
    { key: "avatar_emoji", label: "頭像 emoji", type: "text", hint: "例：🧑‍💻 🎨" },
    { key: "bio", label: "簡介", type: "textarea", rows: 3 },
    { key: "skills", label: "技能（逗號分隔）", type: "json" },
    { key: "email", label: "email", type: "text" },
    { key: "github_url", label: "GitHub URL", type: "text" },
    { key: "sort_order", label: "排序", type: "number", default: 0 },
    { key: "is_active", label: "啟用", type: "boolean", default: true },
  ],
  displayFields: [
    { key: "sort_order", label: "順序", num: true },
    { key: "avatar_emoji", label: "頭像", render: (i) => <span style={{ fontSize: 22 }}>{i.avatar_emoji}</span> },
    { key: "name", label: "姓名" },
    { key: "student_id", label: "學號" },
    { key: "role", label: "角色" },
    { key: "is_active", label: "啟用", render: (i) => i.is_active ? "✓" : "—" },
  ],
};

const RELEASE_SCHEMA = {
  endpoint: "/admin/cms/releases/",
  title: "APP / PWA 版本",
  previewPath: "/download",
  previewLabel: "預覽 /download",
  titleField: "version",
  fields: [
    { key: "version", label: "版本", type: "text", required: true, hint: "例：1.0.0" },
    { key: "platform", label: "平台", type: "select", default: "pwa",
      options: [
        { value: "pwa", label: "PWA（瀏覽器安裝）" },
        { value: "android", label: "Android" },
        { value: "ios", label: "iOS" },
        { value: "desktop", label: "桌面" },
      ] },
    { key: "release_notes", label: "更新說明", type: "textarea", rows: 4 },
    { key: "download_url", label: "下載連結", type: "text", hint: "PWA 留空" },
    { key: "icon_url", label: "圖示 URL", type: "text" },
    { key: "is_latest", label: "標記為最新版", type: "boolean", default: false },
    { key: "is_active", label: "啟用", type: "boolean", default: true },
    { key: "released_at", label: "發布時間", type: "datetime", required: true },
  ],
  displayFields: [
    { key: "version", label: "版本" },
    { key: "platform", label: "平台" },
    { key: "is_latest", label: "最新", render: (i) => i.is_latest ? "✓" : "—" },
    { key: "is_active", label: "啟用", render: (i) => i.is_active ? "✓" : "—" },
  ],
};

const MILESTONE_SCHEMA = {
  endpoint: "/admin/cms/milestones/",
  title: "開發里程碑",
  previewPath: "/project",
  previewLabel: "預覽 /project（timeline）",
  titleField: "title",
  fields: [
    { key: "title", label: "標題", type: "text", required: true },
    { key: "date", label: "日期（YYYY-MM-DD）", type: "text", required: true, hint: "例：2026-06-04" },
    { key: "icon", label: "圖示 emoji", type: "text", hint: "例：🚀 🎯 ✨" },
    { key: "description", label: "說明", type: "textarea", rows: 3 },
    { key: "sort_order", label: "排序", type: "number", default: 0 },
    { key: "is_active", label: "啟用", type: "boolean", default: true },
  ],
  displayFields: [
    { key: "sort_order", label: "順序", num: true },
    { key: "icon", label: "圖示" },
    { key: "title", label: "標題" },
    { key: "date", label: "日期" },
    { key: "is_active", label: "啟用", render: (i) => i.is_active ? "✓" : "—" },
  ],
};

const CONTENT_TABS = [
  { key: "features", label: "🎯 專案特色", schema: FEATURE_SCHEMA },
  { key: "team", label: "👥 團隊成員", schema: TEAM_SCHEMA },
  { key: "releases", label: "📱 APP / PWA 版本", schema: RELEASE_SCHEMA },
  { key: "milestones", label: "🚀 開發里程碑", schema: MILESTONE_SCHEMA },
];

function AdminContentPage() {
  const [tab, setTab] = useState("features");
  const active = CONTENT_TABS.find((t) => t.key === tab);
  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1>內容管理</h1>
        <p>編輯前台公開頁的卡片內容；存檔後前台即時生效</p>
      </header>

      <div className="admin-tab-row">
        {CONTENT_TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            className={`admin-tab ${tab === t.key ? "active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <AdminCmsManager key={tab} schema={active.schema} />
    </div>
  );
}

// 內部成本估算（依 log/2026-06-14_ui-ux-billing-cms-audit.md 中的推算）：
//   - MiniMax M2 token 成本：每 12 頁 scan ≈ NT$0.43
//   - 伺服器月固定費攤提（200 scans/月）：每 scan ≈ NT$7.5
//   - 合計每 scan ≈ NT$8 → 每頁 ≈ NT$0.67（COIN = PAGE）
const COIN_COST_NTD = 0.67;

function planEconomics(plan) {
  const coin = plan.coin_amount || 0;
  const price = plan.price_ntd || 0;
  const cost = Number((coin * COIN_COST_NTD).toFixed(1));
  const margin = price - cost;
  const marginPct = price > 0 ? Math.round((margin / price) * 100) : 0;
  // pages = coin（每頁 10 coin 是 settings 的 ARGUS_COIN_PER_PAGE）
  // 但這裡是「使用者能掃幾頁」直觀感受，所以直接顯示 coin / 10
  const pagesEstimate = Math.floor(coin / 10);
  return { cost, margin, marginPct, pagesEstimate };
}

function AdminSettingsPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/admin/settings/")
      .then((r) => setData(r.data))
      .catch((err) => setError(err.response?.data?.detail || "讀取設定失敗"));
  }, []);

  if (error) return <div className="admin-error">{error}</div>;
  if (!data) return <div className="admin-loading">載入中…</div>;

  const Section = ({ title, rows }) => (
    <section className="admin-panel">
      <h3>{title}</h3>
      <table className="admin-table compact">
        <tbody>
          {rows.map(([k, v]) => {
            let display;
            if (v === true) display = <span className="status-active">是 / 已設定</span>;
            else if (v === false) display = <span className="status-inactive">否 / 未設定</span>;
            else if (Array.isArray(v)) display = v.join(", ");
            else display = String(v);
            return (
              <tr key={k}>
                <td style={{ width: 280, fontFamily: "monospace", color: "#94a3b8" }}>{k}</td>
                <td>{display}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1>系統設定（唯讀）</h1>
        <p>{data.note}</p>
      </header>
      <Section title="計費" rows={Object.entries(data.billing)} />
      <Section title="Hermes-Agent" rows={Object.entries(data.agent)} />
      <Section title="Email 寄送" rows={Object.entries(data.email)} />
      <Section title="第三方登入 / API 金鑰" rows={[
        ...Object.entries(data.auth),
        ...Object.entries(data.providers),
      ]} />
      <Section title="部署" rows={Object.entries(data.deployment)} />
    </div>
  );
}

function AdminPlansPage() {
  const [plans, setPlans] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({});

  useEffect(() => {
    api.get("/admin/cms/plans/").then((r) => setPlans(r.data.items || [])).catch(() => {});
  }, []);

  function openNew() {
    setForm({ name: "", price_ntd: 0, coin_amount: 100, description: "", badge: "", is_active: true, sort_order: 0 });
    setEditing("new");
  }
  function openEdit(plan) {
    setForm({ ...plan });
    setEditing(plan);
  }
  async function handleSave() {
    if (editing === "new") {
      await api.post("/admin/cms/plans/", form);
    } else {
      await api.patch(`/admin/cms/plans/${editing.id}/`, form);
    }
    setEditing(null);
    const r = await api.get("/admin/cms/plans/");
    setPlans(r.data.items || []);
  }
  async function handleDelete(id) {
    if (!window.confirm("確定刪除此方案？")) return;
    await api.delete(`/admin/cms/plans/${id}/`);
    const r = await api.get("/admin/cms/plans/");
    setPlans(r.data.items || []);
  }

  const coinPerNtd = (plan) => plan.price_ntd > 0 ? (plan.coin_amount / plan.price_ntd).toFixed(2) : "—";

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1 className="admin-page-title">方案管理</h1>
        <button className="admin-add-btn" onClick={openNew}>＋ 新增方案</button>
      </header>

      <p className="admin-page-note">
        定價建議：每 coin 內部成本約 NT$ {COIN_COST_NTD}（含 MiniMax token 與伺服器攤提）；
        毛利率 80% 以上算健康，低於 50% 請重新定價。
      </p>

      <div className="admin-plans-grid">
        {plans.map((plan) => {
          const econ = planEconomics(plan);
          const marginTone = econ.marginPct >= 80 ? "good" : econ.marginPct >= 50 ? "warn" : "bad";
          return (
            <div key={plan.id} className={`admin-plan-card ${plan.is_active ? "" : "is-inactive"}`}>
              {plan.badge && <span className="admin-plan-badge">{plan.badge}</span>}
              <h3 className="admin-plan-name">{plan.name}</h3>
              <p className="admin-plan-price">NT$ {(plan.price_ntd || 0).toLocaleString()}</p>
              <p className="admin-plan-coin">{(plan.coin_amount || 0).toLocaleString()} Coin</p>
              <p className="admin-plan-rate">{coinPerNtd(plan)} coin/NT$ · ≈ {econ.pagesEstimate.toLocaleString()} 頁掃描</p>

              <dl className="admin-plan-econ">
                <dt>內部成本</dt>
                <dd>NT$ {econ.cost.toLocaleString()}</dd>
                <dt>毛利</dt>
                <dd className={`tone-${marginTone}`}>
                  NT$ {econ.margin.toLocaleString()}（{econ.marginPct}%）
                </dd>
              </dl>

              {plan.description && <p className="admin-plan-desc">{plan.description}</p>}
              <div className="admin-plan-actions">
                <button onClick={() => openEdit(plan)}>編輯</button>
                <button className="danger" onClick={() => handleDelete(plan.id)}>刪除</button>
                <span className={plan.is_active ? "status-active" : "status-inactive"}>
                  {plan.is_active ? "啟用" : "停用"}
                </span>
              </div>
            </div>
          );
        })}
        {!plans.length && <div className="admin-empty">尚無方案</div>}
      </div>

      {editing && (
        <div className="ann-backdrop">
          <div className="ann-modal" style={{ maxWidth: 480 }}>
            <header className="ann-modal-header">
              <h2 className="ann-modal-title">{editing === "new" ? "新增方案" : "編輯方案"}</h2>
            </header>
            <div className="ann-modal-body" style={{ display: "flex", flexDirection: "column", gap: ".75rem" }}>
              <input className="input" placeholder="名稱" value={form.name || ""} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              <div style={{ display: "flex", gap: ".75rem" }}>
                <input className="input" type="number" placeholder="價格 NT$" value={form.price_ntd || 0} onChange={(e) => setForm({ ...form, price_ntd: Number(e.target.value) })} style={{ width: "50%" }} />
                <input className="input" type="number" placeholder="Coin 數" value={form.coin_amount || 0} onChange={(e) => setForm({ ...form, coin_amount: Number(e.target.value) })} style={{ width: "50%" }} />
              </div>
              <input className="input" placeholder="徽章（選填）" value={form.badge || ""} onChange={(e) => setForm({ ...form, badge: e.target.value })} />
              <textarea className="input" rows={3} placeholder="描述" value={form.description || ""} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              {(() => {
                const e = planEconomics(form);
                const tone = e.marginPct >= 80 ? "good" : e.marginPct >= 50 ? "warn" : "bad";
                return (
                  <div className={`admin-plan-econ-preview tone-${tone}`}>
                    內部成本 NT$ {e.cost} · 毛利 NT$ {e.margin}（{e.marginPct}%） · ≈ {e.pagesEstimate} 頁
                  </div>
                );
              })()}
              <label><input type="checkbox" checked={form.is_active !== false} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> 啟用</label>
            </div>
            <footer className="ann-modal-footer">
              <button className="ann-btn-dismiss" onClick={() => setEditing(null)}>取消</button>
              <button className="ann-btn-confirm" onClick={handleSave}>儲存</button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}

// ------ AdminAuditLogPage（僅超級管理員） ------

const AUDIT_ACTION_OPTIONS = [
  { v: "", label: "全部動作" },
  { v: "coin_adjust", label: "調整點數" },
  { v: "review_reply", label: "回覆評論" },
  { v: "review_delete", label: "刪除評論" },
  { v: "user_toggle_staff", label: "切換管理員身份" },
  { v: "other", label: "其他" },
];

function AdminAnnouncementsPage() {
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ title: "", content: "", type: "temporary", active_days: 7, is_active: true });
  const me = useArgusStore((s) => s.me);

  function loadList() {
    setLoading(true);
    api.get("/admin/announcements/").then((r) => setList(r.data.announcements || [])).finally(() => setLoading(false));
  }
  useEffect(() => {
    if (me?.is_superuser) loadList();
  }, [me]);

  if (!me?.is_superuser) {
    return <div className="admin-error">需要超級管理員權限才能查看。</div>;
  }

  function openNew() {
    setForm({ title: "", content: "", type: "temporary", active_days: 7, is_active: true });
    setEditing("new");
  }
  function openEdit(ann) {
    setForm({ title: ann.title, content: ann.content, type: ann.type, active_days: ann.active_days, is_active: ann.is_active });
    setEditing(ann);
  }
  async function handleSave() {
    if (editing === "new") {
      await api.post("/admin/announcements/", form);
    } else {
      await api.patch(`/admin/announcements/${editing.id}/`, form);
    }
    setEditing(null);
    loadList();
  }
  async function handleDelete(id) {
    if (!window.confirm("確定刪除此公告？")) return;
    await api.delete(`/admin/announcements/${id}/`);
    loadList();
  }

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1 className="admin-page-title">📢 公告管理</h1>
        <button className="admin-add-btn" onClick={openNew}>＋ 新增公告</button>
      </header>

      {loading ? <div className="admin-loading">載入中…</div> : (
        <div className="admin-ann-list">
          {list.map((ann) => (
            <div key={ann.id} className={`admin-ann-card ${ann.is_active ? "" : "inactive"}`}>
              <div className="admin-ann-card-header">
                <span className="admin-ann-title">{ann.title}</span>
                <span className={`admin-ann-type ${ann.type}`}>
                  {ann.type === "permanent" ? "常駐" : `臨時（${ann.active_days}天）`}
                </span>
              </div>
              <p className="admin-ann-preview">{ann.content.slice(0, 80)}…</p>
              <div className="admin-ann-actions">
                <button onClick={() => openEdit(ann)}>編輯</button>
                <button className="danger" onClick={() => handleDelete(ann.id)}>刪除</button>
                <span className={ann.is_active ? "status-active" : "status-inactive"}>
                  {ann.is_active ? "啟用" : "停用"}
                </span>
              </div>
            </div>
          ))}
          {!list.length && <div className="admin-empty">尚無公告</div>}
        </div>
      )}

      {editing && (
        <div className="ann-backdrop">
          <div className="ann-modal" style={{ maxWidth: 560 }}>
            <header className="ann-modal-header">
              <h2 className="ann-modal-title">{editing === "new" ? "新增公告" : "編輯公告"}</h2>
            </header>
            <div className="ann-modal-body" style={{ display: "flex", flexDirection: "column", gap: ".75rem" }}>
              <input className="input" placeholder="標題" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
              <textarea className="input" rows={6} placeholder="內容" value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} />
              <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
                <label><input type="radio" name="type" checked={form.type === "temporary"} onChange={() => setForm({ ...form, type: "temporary" })} /> 臨時公告</label>
                <label><input type="radio" name="type" checked={form.type === "permanent"} onChange={() => setForm({ ...form, type: "permanent" })} /> 常駐公告</label>
              </div>
              {form.type === "temporary" && (
                <label>顯示天數：<input className="input" type="number" min={1} max={365} value={form.active_days} onChange={(e) => setForm({ ...form, active_days: Number(e.target.value) })} style={{ width: 80 }} /></label>
              )}
              <label><input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> 啟用</label>
            </div>
            <footer className="ann-modal-footer">
              <button className="ann-btn-dismiss" onClick={() => setEditing(null)}>取消</button>
              <button className="ann-btn-confirm" onClick={handleSave}>儲存</button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}

function AdminAuditLogPage() {
  const [tab, setTab] = useState("audit");
  const me = useArgusStore((s) => s.me);

  if (!me?.is_superuser) {
    return <div className="admin-error">需要超級管理員權限才能查看。</div>;
  }

  const TABS = [
    { key: "audit", label: "操作紀錄" },
    { key: "transactions", label: "交易紀錄" },
    { key: "scans", label: "掃描紀錄" },
  ];

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1 className="admin-page-title">操作日誌</h1>
        <p>操作/交易/掃描紀錄（僅超級管理員可見）</p>
      </header>

      <div className="admin-sub-tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`admin-sub-tab ${tab === t.key ? "active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="admin-panel">
        {tab === "audit" && <AuditLogTab />}
        {tab === "transactions" && <AdminTransactionsPage embedded />}
        {tab === "scans" && <AdminScansPage embedded />}
      </div>
    </div>
  );
}

function AuditLogTab() {
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [action, setAction] = useState("");

  async function load() {
    const r = await api.get("/admin/audit-log/", {
      params: { page, action: action || undefined },
    });
    setData(r.data);
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [page, action]);

  return (
    <>
      <div className="admin-filter-bar">
        <select
          className="admin-input"
          value={action}
          onChange={(e) => { setAction(e.target.value); setPage(1); }}
        >
          {AUDIT_ACTION_OPTIONS.map((o) => (
            <option key={o.v} value={o.v}>{o.label}</option>
          ))}
        </select>
      </div>

      {!data && <div className="admin-loading">載入中…</div>}
      {data && (
        <>
          <table className="admin-table">
            <thead>
              <tr>
                <th>時間</th>
                <th>動作</th>
                <th>操作者</th>
                <th>對象</th>
                <th>細節</th>
              </tr>
            </thead>
            <tbody>
              {data.logs.map((log) => (
                <tr key={log.id}>
                  <td>{new Date(log.created_at).toLocaleString("zh-Hant")}</td>
                  <td><span className="admin-status">{log.action_label}</span></td>
                  <td><strong>{log.actor_username || "(已刪除)"}</strong></td>
                  <td>{log.target_username || "—"}</td>
                  <td className="admin-cell-secondary">
                    {log.target_object_repr}
                    {Object.keys(log.payload || {}).length > 0 && (
                      <details style={{ marginTop: 4 }}>
                        <summary style={{ cursor: "pointer", color: "#0e7490", fontSize: 11 }}>payload</summary>
                        <pre style={{ fontSize: 11, margin: "4px 0 0", whiteSpace: "pre-wrap" }}>
                          {JSON.stringify(log.payload, null, 2)}
                        </pre>
                      </details>
                    )}
                  </td>
                </tr>
              ))}
              {data.logs.length === 0 && (
                <tr><td colSpan="5" className="admin-empty">尚無紀錄</td></tr>
              )}
            </tbody>
          </table>
          <AdminPagination page={data.page} totalPages={data.total_pages} onChange={setPage} />
        </>
      )}
    </>
  );
}

// ============================================================
// 首次進站粒子過場動畫（移植自 過場動畫和網站設計範本/index.html）
// 階段：STORM → ASSEMBLE → DISPLAY → EXPLODE → WARP，結束呼叫 onComplete。
// 尊重 prefers-reduced-motion：偏好減少動態時直接略過。
// ============================================================

const INTRO_PHASE = { storm: 2000, assemble: 2400, display: 400, warp: 2200 };
const INTRO_TOTAL =
  INTRO_PHASE.storm + INTRO_PHASE.assemble + INTRO_PHASE.display + INTRO_PHASE.warp;
const INTRO_STORM_CHARS = "01ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$&*+={}/<>";
const INTRO_ARGUS_CHARS = "ARGUS";
const INTRO_STORM_COLORS = [
  "rgba(80, 220, 255, 0.55)", "rgba(100, 235, 255, 0.7)", "rgba(60, 200, 240, 0.65)",
  "rgba(140, 240, 255, 0.6)", "rgba(70, 210, 250, 0.75)", "rgba(170, 245, 255, 0.55)",
  "rgba(40, 180, 220, 0.65)", "rgba(110, 230, 255, 0.7)",
];
// 時空穿越光束色盤（沿用開頭動畫的青藍系，不另加雜色）
const INTRO_WARP_COLORS = [
  [56, 189, 248],   // argus-cyan
  [103, 232, 249],  // cyan-glow
  [125, 211, 252],  // sky
  [14, 165, 233],   // cyan-dot
  [150, 220, 255],  // 淺藍
  [224, 242, 254],  // 近白 cyan tint
  [255, 255, 255],  // 白
];

function IntroSequence({ onComplete }) {
  const canvasRef = useRef(null);
  const statusRef = useRef(null);
  const phaseRef = useRef(null);
  const timeRef = useRef(null);
  const fpsRef = useRef(null);
  const countRef = useRef(null);
  const finishRef = useRef(null);
  const completeRef = useRef(onComplete);
  completeRef.current = onComplete;
  const [fading, setFading] = useState(false);

  useEffect(() => {
    const prefersReduced =
      window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReduced) {
      if (completeRef.current) completeRef.current();
      return undefined;
    }
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext("2d", { alpha: true });
    let W = 0, H = 0;
    let particles = [];
    let imgRef = null;
    let logoBox = null;
    let fallbackCanvas = null;
    let warpInited = false;
    let startTime = 0, fpsCount = 0, fpsTimer = 0;
    let mainRAF = null;
    let finished = false;
    let finishTimer = null;

    function resize() {
      W = window.innerWidth; H = window.innerHeight;
      canvas.width = W; canvas.height = H;
    }
    resize();

    function buildLogoBox() {
      if (!imgRef) return;
      const maxW = Math.min(W * 0.6, 720);
      const maxH = Math.min(H * 0.6, 540);
      const ratio = imgRef.width / imgRef.height;
      let tw, th;
      if (maxW / ratio < maxH) { tw = maxW; th = maxW / ratio; }
      else { th = maxH; tw = maxH * ratio; }
      logoBox = { ox: (W - tw) / 2, oy: (H - th) / 2, tw, th };
    }

    function makeParticles(pts) {
      for (let i = pts.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [pts[i], pts[j]] = [pts[j], pts[i]];
      }
      const N = Math.min(pts.length, 1000);
      const cx = W / 2, cy = H / 2;
      const arr = new Array(N);
      for (let i = 0; i < N; i++) {
        const t = pts[i];
        const ang = Math.random() * Math.PI * 2;
        const r0 = Math.max(W, H) * (0.7 + Math.random() * 0.5);
        const isArgus = Math.random() < 0.2;
        arr[i] = {
          tx: t.x, ty: t.y,
          x: cx + Math.cos(ang) * r0, y: cy + Math.sin(ang) * r0,
          r: t.r, g: t.g, b: t.b,
          displayColor: `rgba(${Math.min(255, t.r + 50)}, ${Math.min(255, t.g + 50)}, ${Math.min(255, t.b + 50)}, 0.95)`,
          char: isArgus
            ? INTRO_ARGUS_CHARS[(Math.random() * 5) | 0]
            : INTRO_STORM_CHARS[(Math.random() * INTRO_STORM_CHARS.length) | 0],
          size: [9, 11, 13][(Math.random() * 3) | 0],
          sAng: Math.atan2(t.y - cy, t.x - cx) + (Math.random() - 0.5) * Math.PI,
          sDist: 120 + Math.random() * Math.max(W, H) * 0.5,
          sSpd: 0.5 + Math.random() * 1.5,
          changeTimer: Math.random() * 25,
          eAng: Math.atan2(t.y - cy, t.x - cx) + (Math.random() - 0.5) * 0.4,
          eSpd: 800 + Math.random() * 1400,
          phase: Math.random() * Math.PI * 2,
          locked: false,
        };
      }
      arr.sort((a, b) => a.size - b.size);
      particles = arr;
      if (countRef.current) countRef.current.textContent = String(N);
    }

    function buildFallback() {
      const cx = W / 2, cy = H / 2;
      const s = Math.min(W, H) / 900;
      const off = document.createElement("canvas");
      off.width = W; off.height = H;
      const octx = off.getContext("2d");
      octx.strokeStyle = "#0096ff"; octx.lineWidth = 12 * s;
      octx.beginPath(); octx.ellipse(cx, cy - 30 * s, 260 * s, 110 * s, 0, 0, Math.PI * 2); octx.stroke();
      octx.fillStyle = "#0066cc"; octx.beginPath(); octx.arc(cx, cy - 30 * s, 90 * s, 0, Math.PI * 2); octx.fill();
      octx.fillStyle = "#001a33"; octx.beginPath(); octx.arc(cx, cy - 30 * s, 40 * s, 0, Math.PI * 2); octx.fill();
      octx.fillStyle = "#00aaff";
      octx.font = `bold ${150 * s}px 'Arial Black', 'Impact', sans-serif`;
      octx.textAlign = "center"; octx.textBaseline = "middle";
      octx.fillText("ARGUS", cx, cy + 180 * s);
      fallbackCanvas = off;
      const data = octx.getImageData(0, 0, W, H).data;
      const pts = [];
      for (let y = 0; y < H; y += 5) {
        for (let x = 0; x < W; x += 5) {
          const idx = (y * W + x) * 4;
          if (data[idx + 3] > 80) pts.push({ x, y, r: data[idx], g: data[idx + 1], b: data[idx + 2] });
        }
      }
      makeParticles(pts);
    }

    function buildTargets() {
      if (!imgRef || !logoBox) { buildFallback(); return; }
      const { ox, oy, tw, th } = logoBox;
      const off = document.createElement("canvas");
      off.width = Math.floor(tw); off.height = Math.floor(th);
      const octx = off.getContext("2d");
      octx.drawImage(imgRef, 0, 0, off.width, off.height);
      let data;
      try { data = octx.getImageData(0, 0, off.width, off.height).data; }
      catch (e) { buildFallback(); return; }
      const w = off.width, h = off.height;
      const cornerIdx = [0, (w - 1) * 4, (h - 1) * w * 4, ((h - 1) * w + w - 1) * 4];
      let tCount = 0;
      for (const idx of cornerIdx) if (data[idx + 3] < 30) tCount++;
      const isTransparentBg = tCount >= 3;
      const pts = [];
      const step = 5;
      for (let y = 0; y < h; y += step) {
        for (let x = 0; x < w; x += step) {
          const idx = (y * w + x) * 4;
          const r = data[idx], g = data[idx + 1], b = data[idx + 2], a = data[idx + 3];
          let keep;
          if (isTransparentBg) keep = a > 40;
          else {
            const lum = (r + g + b) / 3 / 255;
            const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
            const sat = mx === 0 ? 0 : (mx - mn) / mx;
            keep = a > 60 && !(lum > 0.93 && sat < 0.06);
          }
          if (keep) pts.push({ x: ox + x, y: oy + y, r, g, b });
        }
      }
      makeParticles(pts);
    }

    function randomizeWarp(p) {
      // 不規則：每粒子隨機顏色 / 寬度 / 拉長長度 / 速度
      p.warpColor = INTRO_WARP_COLORS[(Math.random() * INTRO_WARP_COLORS.length) | 0];
      p.warpWidth = 2 + Math.random() * 9;        // 粗細不一
      p.warpLenK = 0.7 + Math.random() * 2.8;     // 拉長長度不一
      p.warpSpeedK = 0.6 + Math.random() * 1.2;   // 速度不一
    }
    function initWarp() {
      // 從粒子「目前位置」(剛聚合成 logo 的位置) 直接往外發射 →
      // logo 散開無縫接上時空穿越，中間不經過白色閃光。
      const cx = W / 2, cy = H / 2;
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        const dx = p.x - cx, dy = p.y - cy;
        p.warpAng = Math.atan2(dy, dx);
        p.warpDist = Math.max(2, Math.hypot(dx, dy));
        randomizeWarp(p);
      }
    }

    function updateAndDraw(phase, pt, elapsed) {
      const cx = W / 2, cy = H / 2;
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      let lastSize = -1;
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        if (phase === "STORM") {
          const settle = pt * pt; const chaos = 1 - settle * 0.6;
          p.sAng += p.sSpd * 0.011 * chaos;
          p.sDist -= settle * 1.4;
          const maxR = Math.max(W, H) * (0.7 - settle * 0.35);
          if (p.sDist < 60) p.sDist = 60; if (p.sDist > maxR) p.sDist = maxR;
          const slow = elapsed * 0.001;
          const w1 = Math.sin(slow + p.phase) * 50 * chaos;
          const w2 = Math.cos(slow * 1.4 + p.phase * 2.3) * 35 * chaos;
          const driftX = Math.sin(slow * 0.6 + p.phase * 3.7) * 28 * chaos;
          const driftY = Math.cos(slow * 0.9 + p.phase * 1.7) * 32 * chaos;
          const r = p.sDist + w1 + w2;
          const sx = cx + Math.cos(p.sAng) * r * 1.3 + driftX;
          const sy = cy + Math.sin(p.sAng) * r * 0.8 + driftY;
          const lerpK = Math.max(0, settle - 0.15) * 0.11;
          p.x = sx + (p.tx - sx) * lerpK; p.y = sy + (p.ty - sy) * lerpK;
          p.changeTimer--;
          if (p.changeTimer < 0) {
            p.char = INTRO_STORM_CHARS[(Math.random() * INTRO_STORM_CHARS.length) | 0];
            p.changeTimer = 10 + Math.random() * 25;
          }
        } else if (phase === "ASSEMBLE") {
          const k = 0.08 + pt * 0.09;
          p.x += (p.tx - p.x) * k; p.y += (p.ty - p.y) * k;
          if (pt > 0.8) {
            const blend = (pt - 0.8) / 0.2;
            const breath = Math.sin(elapsed * 0.003 + p.phase) * 1;
            p.x = p.x * (1 - blend) + (p.tx + breath) * blend;
            p.y = p.y * (1 - blend) + (p.ty + breath * 0.5) * blend;
          }
          if (pt > 0.6 && !p.locked) {
            const inText = (p.ty - cy) > 60;
            if (inText && Math.random() < 0.55) p.char = INTRO_ARGUS_CHARS[(Math.random() * 5) | 0];
            p.locked = true;
          } else if (!p.locked) {
            p.changeTimer--;
            if (p.changeTimer < 0) {
              p.char = INTRO_STORM_CHARS[(Math.random() * INTRO_STORM_CHARS.length) | 0];
              p.changeTimer = 10 + Math.random() * 20;
            }
          }
        } else if (phase === "DISPLAY") {
          const breath = Math.sin(elapsed * 0.003 + p.phase) * 1;
          p.x = p.tx + breath; p.y = p.ty + breath * 0.5;
        }
        let fill;
        if (phase === "STORM") fill = INTRO_STORM_COLORS[i & 7];
        else if (phase === "ASSEMBLE") fill = pt > 0.5 ? p.displayColor : INTRO_STORM_COLORS[i & 7];
        else fill = p.displayColor;
        if (p.size !== lastSize) { ctx.font = `bold ${p.size}px 'Consolas', monospace`; lastSize = p.size; }
        ctx.fillStyle = fill;
        ctx.fillText(p.char, p.x, p.y);
      }
    }

    function mainLoop(now) {
      const elapsed = now - startTime;
      fpsCount++;
      if (now - fpsTimer > 500) {
        if (fpsRef.current) fpsRef.current.textContent = String(Math.round(fpsCount * 1000 / (now - fpsTimer)));
        fpsCount = 0; fpsTimer = now;
      }
      if (timeRef.current) timeRef.current.textContent = (elapsed / 1000).toFixed(1).padStart(4, "0");
      const P = INTRO_PHASE;
      let phaseName, pt;
      if (elapsed < P.storm) { phaseName = "STORM"; pt = elapsed / P.storm; }
      else if (elapsed < P.storm + P.assemble) { phaseName = "ASSEMBLE"; pt = (elapsed - P.storm) / P.assemble; }
      else if (elapsed < P.storm + P.assemble + P.display) { phaseName = "DISPLAY"; pt = (elapsed - P.storm - P.assemble) / P.display; }
      else if (elapsed < INTRO_TOTAL) { phaseName = "WARP"; pt = (elapsed - P.storm - P.assemble - P.display) / P.warp; }
      else { if (finishRef.current) finishRef.current(); return; }
      if (phaseRef.current) phaseRef.current.textContent = phaseName;
      const STATUS_MAP = { STORM: "ANALYZING", ASSEMBLE: "CONVERGING", DISPLAY: "LOCKED-ON", WARP: "HYPERSPACE" };
      if (statusRef.current) statusRef.current.textContent = STATUS_MAP[phaseName];

      if (phaseName === "WARP") {
        if (!warpInited) { initWarp(); warpInited = true; }
        const zoom = 1 + pt * pt * 0.65;
        canvas.style.transform = `scale(${zoom})`;
        // 觀測者越來越快 → 每幀清除越少、上一幀殘留越久 → 粒子拉出長殘影拖曳
        const trailFade = Math.max(0.05, 0.2 - pt * 0.15);
        ctx.fillStyle = `rgba(12, 16, 38, ${trailFade})`;
        ctx.fillRect(0, 0, W, H);
        const cxw = W / 2, cyw = H / 2;
        const baseSpeed = 5 + pt * pt * 80;
        const maxD = Math.max(W, H) * 1.35;
        for (let i = 0; i < particles.length; i++) {
          const p = particles[i];
          p.warpDist += baseSpeed * p.warpSpeedK;
          if (p.warpDist > maxD) {
            // 回收：隨機角度 + 重抽顏色/寬/長 → 持續不規則放射
            p.warpDist = Math.random() * 40;
            p.warpAng = Math.random() * Math.PI * 2;
            randomizeWarp(p);
          }
          const cosA = Math.cos(p.warpAng), sinA = Math.sin(p.warpAng);
          const x = cxw + cosA * p.warpDist, y = cyw + sinA * p.warpDist;
          // 拉長：長度隨距離增加且每粒子不一
          const tailLen = (baseSpeed * 1.5 + p.warpDist * 0.3) * p.warpLenK;
          const tx = cxw + cosA * (p.warpDist - tailLen), ty = cyw + sinA * (p.warpDist - tailLen);
          // 外端寬、內端收尖的錐形（垂直方向取半寬）
          const hw = p.warpWidth * Math.min(1, p.warpDist / 200);
          const px = -sinA, py = cosA;
          const a = Math.min(0.82, p.warpDist / 130);
          const c = p.warpColor;
          ctx.fillStyle = `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${a})`;
          ctx.beginPath();
          ctx.moveTo(tx, ty);                   // 內端尖點
          ctx.lineTo(x + px * hw, y + py * hw); // 外端一側
          ctx.lineTo(x - px * hw, y - py * hw); // 外端另一側
          ctx.closePath();
          ctx.fill();
        }
        mainRAF = requestAnimationFrame(mainLoop);
        return;
      }

      ctx.clearRect(0, 0, W, H);
      let logoAlpha = 0;
      if (phaseName === "ASSEMBLE") logoAlpha = pt * 0.9;
      else if (phaseName === "DISPLAY") logoAlpha = 0.9 + Math.sin(elapsed * 0.003) * 0.08;
      if (logoAlpha > 0) {
        ctx.save(); ctx.globalAlpha = logoAlpha;
        if (imgRef && logoBox) ctx.drawImage(imgRef, logoBox.ox, logoBox.oy, logoBox.tw, logoBox.th);
        else if (fallbackCanvas) ctx.drawImage(fallbackCanvas, 0, 0);
        ctx.restore();
      }
      updateAndDraw(phaseName, pt, elapsed);
      mainRAF = requestAnimationFrame(mainLoop);
    }

    function finish() {
      if (finished) return;
      finished = true;
      if (mainRAF) cancelAnimationFrame(mainRAF);
      setFading(true);
      finishTimer = window.setTimeout(() => { if (completeRef.current) completeRef.current(); }, 650);
    }
    finishRef.current = finish;

    const onResize = () => { resize(); if (imgRef) buildLogoBox(); };
    window.addEventListener("resize", onResize);
    // 點畫面任一處 / Esc / Enter / 空白鍵 皆可跳過動畫
    const onKey = (e) => {
      if (e.key === "Escape" || e.key === "Enter" || e.key === " ") { e.preventDefault(); finish(); }
    };
    window.addEventListener("keydown", onKey);

    const img = new Image();
    img.onload = () => { imgRef = img; buildLogoBox(); buildTargets(); startTime = performance.now(); fpsTimer = startTime; mainRAF = requestAnimationFrame(mainLoop); };
    img.onerror = () => { buildFallback(); startTime = performance.now(); fpsTimer = startTime; mainRAF = requestAnimationFrame(mainLoop); };
    img.src = introLogo;

    return () => {
      window.removeEventListener("resize", onResize);
      window.removeEventListener("keydown", onKey);
      if (mainRAF) cancelAnimationFrame(mainRAF);
      if (finishTimer) clearTimeout(finishTimer);
    };
  }, []);

  return (
    <div
      className={`argus-intro ${fading ? "argus-intro--out" : ""}`}
      role="presentation"
      onClick={() => { if (finishRef.current) finishRef.current(); }}
    >
      <div className="argus-intro-grid" />
      <canvas ref={canvasRef} className="argus-intro-canvas" />
      <span className="argus-intro-corner tl" />
      <span className="argus-intro-corner tr" />
      <span className="argus-intro-corner bl" />
      <span className="argus-intro-corner br" />
      <div className="argus-intro-hud tl">
        <span className="dim">SYS://</span> <span className="v">ARGUS-CORE</span><br />
        <span className="dim">VER</span> <span className="v">v3.14.59</span><br />
        <span className="dim">NODE</span> <span className="v">ATHENS-07</span>
      </div>
      <div className="argus-intro-hud tr">
        <span className="dim">STATUS</span> <span className="v" ref={statusRef}>STAND-BY</span><br />
        <span className="dim">PHASE</span> <span className="v" ref={phaseRef}>--</span><br />
        <span className="dim">TIME</span> <span className="v" ref={timeRef}>00.0</span><span className="dim">s</span>
      </div>
      <div className="argus-intro-hud br">
        <span className="dim">PARTICLES</span> <span className="v" ref={countRef}>0</span><br />
        <span className="dim">FPS</span> <span className="v" ref={fpsRef}>--</span>
      </div>
      <div className="argus-intro-hint">點擊任意處跳過</div>
    </div>
  );
}

// ============================================================
// 根 App + Routes
// ============================================================

function NotFoundPage() {
  const accessToken = useArgusStore((s) => s.accessToken);
  return (
    <div className="public-shell">
      <section className="public-hero">
        <div className="public-hero-content" style={{ textAlign: "center" }}>
          <span className="public-hero-eyebrow">404 · 找不到頁面</span>
          <h1 className="public-hero-title">
            這個頁面<span className="hero-grad">不存在</span>
          </h1>
          <p className="public-hero-sub">
            您嘗試訪問的網址不在 Argus 上，可能是連結已失效、輸入錯誤，或頁面已被移除。
          </p>
          <div
            style={{
              display: "flex",
              gap: "0.75rem",
              justifyContent: "center",
              flexWrap: "wrap",
              marginTop: "1.5rem",
            }}
          >
            <Link
              to={accessToken ? "/dashboard" : "/project"}
              className="public-cta-primary"
            >
              {accessToken ? "回 Dashboard" : "回首頁"}
            </Link>
            <Link to="/free-tools" className="public-cta-ghost">
              免費快速檢查
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}

function AppShell() {
  const accessToken = useArgusStore((state) => state.accessToken);
  const location = useLocation();
  const navigate = useNavigate();
  const isAdmin = location.pathname.startsWith("/admin");
  const isPublic = ["/project", "/free-tools", "/team", "/purchase", "/download", "/reviews"].some((p) =>
    location.pathname.startsWith(p),
  );
  const showTopNav = !isAdmin && !isPublic;
  // 首次進站才播過場動畫（旗標在 store/localStorage）；品牌 ⟡ icon 可呼叫 replayIntro 重播
  const introSeen = useArgusStore((s) => s.introSeen);
  const markIntroSeen = useArgusStore((s) => s.markIntroSeen);
  function handleIntroDone() {
    markIntroSeen();
    // 播完一律導向首頁 /project（含已登入者；唯獨 /login 不覆寫，讓登入流程自身導向）
    if (location.pathname !== "/login") {
      navigate("/project", { replace: true });
    }
  }
  return (
    <div className={`argus-app ${isAdmin ? "is-admin-mode" : ""} ${isPublic ? "is-public-mode" : ""}`}>
      {!introSeen && <IntroSequence onComplete={handleIntroDone} />}
      {showTopNav && <TopNav />}
      <main className={`argus-main ${accessToken && showTopNav ? "with-nav" : ""} ${isAdmin ? "is-admin" : ""} ${isPublic ? "is-public" : ""}`}>
        <Routes>
          <Route path="/" element={<Navigate to={accessToken ? "/dashboard" : "/project"} replace />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/password-reset" element={<PasswordResetRequestPage />} />
          <Route path="/password-reset/confirm" element={<PasswordResetConfirmPage />} />
          <Route element={<PublicLayout />}>
            <Route path="/project" element={<ProjectPage />} />
            <Route path="/free-tools" element={<FreeToolsPage />} />
            <Route path="/team" element={<TeamPage />} />
            <Route path="/purchase" element={<PurchasePage />} />
            <Route path="/download" element={<DownloadPage />} />
            <Route path="/reviews" element={<ReviewsPage />} />
          </Route>
          <Route
            path="/dashboard"
            element={
              <RequireAuth>
                <DashboardPage />
              </RequireAuth>
            }
          />
          <Route
            element={
              <RequireAuth>
                <ScanLayout />
              </RequireAuth>
            }
          >
            <Route path="/scans" element={<ScansPlaceholder />} />
            <Route path="/scans/:scanId" element={<ScanDetailPage />} />
            <Route path="/scans/:scanId/topology" element={<TopologyPage />} />
          </Route>
          <Route
            path="/history"
            element={
              <RequireAuth>
                <HistoryPage />
              </RequireAuth>
            }
          />
          <Route
            path="/billing"
            element={
              <RequireAuth>
                <BillingPage />
              </RequireAuth>
            }
          />
          <Route
            path="/settings"
            element={
              <RequireAuth>
                <SettingsPage />
              </RequireAuth>
            }
          />
          <Route
            element={
              <RequireAdmin>
                <AdminLayout />
              </RequireAdmin>
            }
          >
            <Route path="/admin" element={<Navigate to="/admin/overview" replace />} />
            <Route path="/admin/overview" element={<AdminOverviewPage />} />
            <Route path="/admin/users" element={<AdminUsersPage />} />
            <Route path="/admin/users/:userId" element={<AdminUserDetailPage />} />
            <Route path="/admin/transactions" element={<AdminTransactionsPage />} />
            <Route path="/admin/reviews" element={<AdminReviewsPage />} />
            <Route path="/admin/scans" element={<AdminScansPage />} />
            <Route path="/admin/scans/:scanId" element={<AdminScanDetailPage />} />
            <Route path="/admin/content" element={<AdminContentPage />} />
            <Route path="/admin/plans" element={<AdminPlansPage />} />
            <Route path="/admin/settings" element={<AdminSettingsPage />} />
            <Route path="/admin/audit-log" element={<AdminAuditLogPage />} />
            <Route path="/admin/announcements" element={<AdminAnnouncementsPage />} />
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return <AppShell />;
}
