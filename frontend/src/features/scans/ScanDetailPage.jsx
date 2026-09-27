import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api } from "../../api";
import FindingDetail from "../../components/scans/FindingDetail.jsx";
import FindingsGroupList from "../../components/scans/FindingsGroupList.jsx";
import FixOutputSection from "../../components/scans/FixOutputSection.jsx";
import PageRebuildPanel from "../../components/scans/PageRebuildPanel.jsx";
import ReportHeader from "../../components/scans/ReportHeader.jsx";
import ReportSummary from "../../components/scans/ReportSummary.jsx";
import ScanProgress from "../../components/scans/ScanProgress.jsx";
import ScreenshotViewer from "../../components/scans/ScreenshotViewer.jsx";
import { ArgusMark } from "../../components/brand/ArgusMark";
import {
  CATEGORY_FILTERS,
  SEVERITY_FILTERS,
  isInProgress,
  useConfirmDialogs,
} from "../../shared/AppShared.jsx";

const SCAN_POLL_INTERVAL_MS = 2000;

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
    const { data } = await api.get(`${path}${separator}page_size=${LIST_PAGE_SIZE}&page=${page}`);
    // 端點若未啟用分頁會直接回陣列，此時第一次就取完了
    if (Array.isArray(data)) return data;
    items.push(...(data.results || []));
    if (!data.next) break;
  }
  return items;
}

function formatLogTime(value) {
  return new Date(value).toLocaleTimeString("zh-TW", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** 篩選 chip 列：色＋文字＋數量，比下拉選單少一次點擊、也看得到每一類有幾筆。 */
function FilterChips({ label, options, value, counts, onChange, kind }) {
  return (
    <div className="filter-chips" role="group" aria-label={label}>
      <span className="filter-chips-label">{label}</span>
      {options.map((option) => {
        const count = option.value === "all" ? counts.all : counts[option.value] || 0;
        const selected = value === option.value;
        return (
          <button
            key={option.value}
            type="button"
            className={`filter-chip ${kind}-${option.value} ${selected ? "active" : ""} ${count ? "" : "is-zero"}`}
            aria-pressed={selected}
            onClick={() => onChange(option.value)}
          >
            {option.value !== "all" && <span className="filter-chip-dot" aria-hidden="true" />}
            {option.value === "all" ? "全部" : option.label}
            <span className="filter-chip-count ag-num">{count}</span>
          </button>
        );
      })}
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
  const [detailsLoaded, setDetailsLoaded] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [cancelBusy, setCancelBusy] = useState(false);
  const [downloading, setDownloading] = useState(false);
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
      } finally {
        if (!cancelled) setDetailsLoaded(true);
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

  function clearSelection() {
    const params = new URLSearchParams(searchParams);
    params.delete("finding");
    setSearchParams(params, { replace: false });
  }

  function selectTopAction(action) {
    // 試著從現有 findings 找符合的 finding 自動選中
    const matched = findings.find((f) => f.category === action.category && f.title === action.title);
    if (matched) {
      selectFinding(matched);
      document.getElementById("report-workspace")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  async function downloadReport() {
    setDownloading(true);
    try {
      const response = await api.get(`/scans/${scan.id}/report/`, {
        responseType: "blob",
      });
      const url = URL.createObjectURL(response.data);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `argus-scan-${scan.id}-report.docx`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      notifyDialog("匯出失敗，請稍後再試。");
    } finally {
      setDownloading(false);
    }
  }

  // page tab 過濾：「all」顯示全部、某 page id 顯示該頁與站台級 finding
  const pageFiltered =
    pageTabParam === "all"
      ? findings
      : findings.filter((f) => String(f.page) === pageTabParam || f.page === null);

  const filteredFindings = pageFiltered.filter(
    (finding) =>
      (categoryFilter === "all" || finding.category === categoryFilter) &&
      (severityFilter === "all" || finding.severity === severityFilter),
  );

  // 篩選 chip 上的數字：嚴重度計數套用分類篩選、分類計數套用嚴重度篩選，
  // 這樣數字永遠等於「點下去會看到幾筆」。
  const severityCounts = useMemo(() => {
    const counts = { all: 0 };
    for (const f of pageFiltered) {
      if (categoryFilter !== "all" && f.category !== categoryFilter) continue;
      counts.all += 1;
      counts[f.severity] = (counts[f.severity] || 0) + 1;
    }
    return counts;
  }, [pageFiltered, categoryFilter]);
  const categoryCounts = useMemo(() => {
    const counts = { all: 0 };
    for (const f of pageFiltered) {
      if (severityFilter !== "all" && f.severity !== severityFilter) continue;
      counts.all += 1;
      counts[f.category] = (counts[f.category] || 0) + 1;
    }
    return counts;
  }, [pageFiltered, severityFilter]);

  // 截圖目標 page：page tab 指定為某 page → 用它；tab=all → 用 selectedFinding 的 page 或 pages[0]
  const targetPage =
    pageTabParam !== "all"
      ? pages.find((p) => String(p.id) === pageTabParam)
      : (selectedFinding?.page && pages.find((p) => p.id === selectedFinding.page)) || pages[0] || null;

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

  const inProgress = isInProgress(scan.status);
  const hasFindings = findingStats?.total > 0 || findings.length > 0;
  const selectedPage = selectedFinding?.page ? pages.find((p) => p.id === selectedFinding.page) : null;
  const selectedPageLabel = selectedFinding
    ? selectedPage?.url || selectedPage?.final_url || "站台層級（不屬於單一頁面）"
    : "";
  const blockedCount = scan.warning_summary?.blocked_urls?.length || 0;

  return (
    <div className="report">
      <ReportHeader scan={scan} onDownload={downloadReport} downloading={downloading} />

      {inProgress && (
        <div className="report-progress">
          <ScanProgress
            status={scan.status}
            scanMode={scan.scan_mode}
            progress={scan.progress}
            startedAt={scan.started_at}
            onCancel={handleCancel}
            cancelBusy={cancelBusy}
            hint={`畫面每 ${SCAN_POLL_INTERVAL_MS / 1000} 秒自動更新；可以離開此頁，掃描會在背景繼續`}
          />
          <p className="report-note">
            為避免無意義的建議，後台路徑（/admin、/wp-admin、/dashboard 等）會跳過 SEO／AEO／GEO
            評分（安全標頭與 CSRF 仍會檢查）；.apk、.zip、.pdf、圖片等下載連結不會列入頁面分析。
          </p>
          {blockedCount > 0 && (
            <p className="report-note is-warn">已偵測到 {blockedCount} 個被阻擋的 URL（403／429／robots.txt）。</p>
          )}
        </div>
      )}

      {scan.status === "failed" && (
        <div className="report-callout is-bad" role="alert">
          <p className="report-callout-title">掃描失敗</p>
          <p>{scan.error_message || "未知錯誤"}</p>
        </div>
      )}

      {scan.status === "cancelled" && (
        <div className="report-callout is-muted" role="status">
          <p className="report-callout-title">掃描已終止</p>
          <p>已收集到的頁面與問題仍保留在下方。</p>
        </div>
      )}

      {(hasFindings || scan.status === "completed") && (
        <ReportSummary
          severityTotals={severityTotals}
          categoryTotals={categoryTotals}
          topActions={scan.top_actions}
          inProgress={inProgress}
          showCharts={hasFindings}
          onSelectAction={selectTopAction}
        />
      )}

      {/* 掃描執行 Log */}
      {scan.scan_log?.length > 0 && (
        <details className="report-log">
          <summary className="report-log-summary">
            執行日誌
            <span className="report-log-count ag-num">{scan.scan_log.length} 筆</span>
          </summary>
          <ol className="report-log-body">
            {scan.scan_log.map((entry, i) => (
              <li key={i} className={`report-log-entry is-${entry.lvl}`}>
                <span className="report-log-time">{formatLogTime(entry.t)}</span>
                <span className="report-log-lvl">{entry.lvl === "error" ? "ERR" : entry.lvl === "warn" ? "WRN" : "INF"}</span>
                <span className="report-log-msg">{entry.msg}</span>
              </li>
            ))}
          </ol>
        </details>
      )}

      <section className="panel report-workspace" id="report-workspace" aria-labelledby="report-workspace-title">
        <header className="report-workspace-head">
          <div>
            <p className="ag-eyebrow">逐頁檢視</p>
            <h2 className="section-title" id="report-workspace-title">
              截圖與問題清單
            </h2>
          </div>
          {pages.length > 0 && (
            <p className="report-workspace-meta">
              {pages.length} 頁・站台層級 {findingsPerPage.siteLevel} 項
            </p>
          )}
        </header>

        {/* 頁面 tabs：依不同頁面切換截圖區與 findings 範圍 */}
        {pages.length > 0 && (
          <div className="page-tabs" role="group" aria-label="頁面">
            <button
              type="button"
              className={`page-tab ${pageTabParam === "all" ? "active" : ""}`}
              onClick={() => setPageTab("all")}
              aria-pressed={pageTabParam === "all"}
            >
              <span className="page-tab-label">全站</span>
              <span className="page-tab-count">{findings.length}</span>
            </button>
            {pages.map((page) => {
              const isHome = page.depth === 0;
              const urlPath = (page.url || "").replace(scan.origin, "").split("?")[0].replace(/^\//, "");
              // 標籤優先用 page.title（更語意化），缺則 fallback 到 URL path
              // 截斷統一 18 字並加 ellipsis，避免「p/412-1000-172.ph」這種被切掉副檔名字尾的歧義
              const rawLabel = page.title?.trim() || urlPath || `Page ${page.id}`;
              const label = isHome ? "首頁" : rawLabel.length > 18 ? rawLabel.slice(0, 18) + "…" : rawLabel;
              const cnt = findingsPerPage.perPage.get(page.id) || 0;
              const active = String(page.id) === pageTabParam;
              return (
                <button
                  key={page.id}
                  type="button"
                  className={`page-tab ${active ? "active" : ""}`}
                  onClick={() => setPageTab(page.id)}
                  title={page.url}
                  aria-pressed={active}
                >
                  <span className="page-tab-label">{label}</span>
                  <span className="page-tab-count">{cnt}</span>
                </button>
              );
            })}
          </div>
        )}

        {!detailsLoaded ? (
          <div className="report-workspace-loading" aria-busy="true">
            <span className="report-skel is-tall" />
            <span className="report-skel" />
          </div>
        ) : (
          <div className="report-workspace-grid">
            <div className="report-workspace-main">
              <ScreenshotViewer
                findings={filteredFindings}
                targetPage={targetPage}
                scan={scan}
                selectedFinding={selectedFinding}
                onSelectFinding={selectFinding}
              />
              {/* 複刻是「針對某一頁」的產出，全站頁籤下沒有明確對象時用第一頁；
                  key 讓面板隨頁面重新掛載：不這樣做的話，切頁籤時前一頁還在跑的
                  polling 會把舊結果寫進新頁面的狀態。 */}
              {targetPage && <PageRebuildPanel key={targetPage.id} scan={scan} page={targetPage} />}
            </div>
            <aside className="report-workspace-side" aria-label="問題清單">
              <div className="report-filters">
                <FilterChips
                  label="嚴重度"
                  kind="sev"
                  options={SEVERITY_FILTERS}
                  value={severityFilter}
                  counts={severityCounts}
                  onChange={setSeverityFilter}
                />
                <FilterChips
                  label="分類"
                  kind="cat"
                  options={CATEGORY_FILTERS}
                  value={categoryFilter}
                  counts={categoryCounts}
                  onChange={setCategoryFilter}
                />
              </div>
              {selectedFinding && (
                <FindingDetail
                  key={selectedFinding.id}
                  finding={selectedFinding}
                  pageLabel={selectedPageLabel}
                  onClose={clearSelection}
                />
              )}
              <FindingsGroupList
                findings={filteredFindings}
                pages={pages}
                scanStatus={scan.status}
                totalFindings={findings.length}
                selectedFinding={selectedFinding}
                onSelectFinding={selectFinding}
              />
            </aside>
          </div>
        )}
      </section>

      {/* 修正產出專區：全寬獨立區塊，只在掃描完成後出現——進行中的掃描
          沒有完整爬取內容可當事實基礎，也不該讓使用者誤觸計費。 */}
      {scan.status === "completed" && <FixOutputSection scan={scan} />}
      {dialogHost}
    </div>
  );
}

/** 報告頁的載入骨架：標頭＋摘要三卡的輪廓。 */
function ReportSkeleton() {
  return (
    <div className="report" aria-busy="true" aria-label="載入掃描資料中">
      <div className="panel report-head is-skeleton">
        <div className="report-head-main">
          <span className="report-skel is-short" />
          <span className="report-skel is-title" />
          <span className="report-skel is-short" />
        </div>
        <ArgusMark size={72} scanning />
      </div>
      <div className="report-summary">
        <span className="panel report-skel-card" />
        <span className="panel report-skel-card" />
        <span className="panel report-skel-card" />
      </div>
    </div>
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
      <section className="panel scan-state-card" role="alert">
        <ArgusMark size={48} />
        <p className="scan-state-title">找不到這份報告</p>
        <p className="hint-text">{loadError}</p>
        <button className="secondary-button" type="button" onClick={() => navigate("/scans")}>
          回到掃描列表
        </button>
      </section>
    );
  }
  // 換掃描時舊資料不能先頂著：scanId 與資料不符就顯示骨架
  if (scan && String(scan.id) === String(scanId)) {
    return <FindingsWorkspace key={scan.id} scan={scan} />;
  }
  return <ReportSkeleton />;
}

export { ScanDetailPage };
