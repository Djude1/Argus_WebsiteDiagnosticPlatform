import { useEffect, useMemo, useRef, useState } from "react";
import {
  Outlet,
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

import { api } from "../../api";
import NavActions from "../../components/navigation/NavActions.jsx";
import { ScanStatusBadge, ScoreBadge } from "../../components/scans/ScanBadges.jsx";
import { useArgusStore } from "../../store";
import {
  CATEGORY_COLOR,
  CATEGORY_FILTERS,
  CATEGORY_LABELS,
  SEVERITY_FILTERS,
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

// localStorage 暫存表單草稿的 key
const SCAN_DRAFT_KEY = "argus_scan_draft_v1";

// ============================================================
// 通用小元件
// ============================================================

// 四階段進度條：等待 → 爬取 → 掃描 → Agent 測試 → 完成
const CRAWL_PHASES = [
  { key: "queued", label: "等待", Icon: StatusQueuedGlyph },
  { key: "crawling", label: "爬取", Icon: StatusCrawlGlyph },
  { key: "scanning", label: "掃描", Icon: StatusScanGlyph },
  { key: "agent_testing", label: "Agent", Icon: StatusAgentGlyph },
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
        <span className="crawl-anim-spider" aria-hidden="true"><current.Icon className="crawl-anim-glyph" /></span>
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
                {idx < safeIdx ? <StatusDoneGlyph /> : <phase.Icon />}
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
      const res = await api.post("/estimate/", { url, max_pages: effectivePages });
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
        const [findingsResponse, pagesResponse, statsResponse] = await Promise.all([
          api.get(`/findings/?scan_id=${scan.id}`),
          api.get(`/pages/?scan_id=${scan.id}`),
          api.get(`/scans/${scan.id}/finding-stats/`),
        ]);
        if (cancelled) return;
        setFindings(findingsResponse.data.results || findingsResponse.data);
        setPages(pagesResponse.data.results || pagesResponse.data);
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

  return (
    <>
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
      {(findingStats?.total > 0 || findings.length > 0) && (
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
    {dialogHost}
    </>
  );
}

// ============================================================
// 路由保護與版面
// ============================================================

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

export {
  ScanLayout,
  ScansPlaceholder,
  ScanDetailPage,
  TopologyPage,
};
