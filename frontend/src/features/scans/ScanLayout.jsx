import { useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate, useOutletContext, useParams } from "react-router-dom";

import { api } from "../../api";
import { ArgusMark } from "../../components/brand/ArgusMark";
import ScanJobForm from "../../components/scans/ScanJobForm.jsx";
import ScanList, { LIST_POLL_INTERVAL_MS } from "../../components/scans/ScanList.jsx";
import { isInProgress } from "../../shared/AppShared.jsx";
import { LayersIcon, SpiderIcon } from "../../shared/LineIcons.jsx";

// ============================================================
// 路由保護與版面
// ============================================================

// ScanLayout 是 parent route + Outlet：表單與列表只 mount 一次，
// `/scans` ↔ `/scans/:id` 切換只重渲染 Outlet，避免每次按「建立掃描」
// 版面整個 unmount 再 remount 造成的跳動。
//
// 兩種模式：
//   list-mode（/scans）：左欄建立表單、右欄是工作台概覽＋掃描列表。
//   detail-mode（/scans/:id）：表單與列表收進左側抽屜，報告拿到全寬讓截圖變大。

function ScanLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { scanId } = useParams();
  const isDetailPage = Boolean(scanId);
  const isTopologyPage = isDetailPage && location.pathname.endsWith("/topology");
  const [scans, setScans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);

  async function loadScans() {
    try {
      const response = await api.get("/scans/");
      setScans(response.data.results || response.data);
    } catch {
      // 401 之類靜默失敗，store 變動會自動導回 /login
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadScans();
  }, []);

  // 從詳情頁切回列表頁時，自動關閉 drawer 避免 inline sidebar 與 drawer 同時出現
  useEffect(() => {
    if (!isDetailPage) setDrawerOpen(false);
  }, [isDetailPage]);

  // 抽屜開著時 Esc 可關
  useEffect(() => {
    if (!drawerOpen) return undefined;
    function onKey(event) {
      if (event.key === "Escape") setDrawerOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

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

  const list = <ScanList scans={scans} loading={loading} onRefresh={loadScans} />;

  return (
    <div className={`scan-layout ${isDetailPage ? "detail-mode" : "list-mode"} ${drawerOpen ? "drawer-open" : ""}`}>
      <aside
        className="scan-sidebar"
        id="scan-sidebar"
        aria-label="建立掃描與掃描列表"
        // 抽屜收起時不該被 Tab 走進去
        inert={isDetailPage && !drawerOpen ? "" : undefined}
      >
        <ScanJobForm onCreated={handleScanCreated} />
        {isDetailPage && list}
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
          <nav className="scan-content-toolbar" aria-label="報告導覽">
            <button
              type="button"
              className="drawer-toggle"
              onClick={() => setDrawerOpen((open) => !open)}
              aria-expanded={drawerOpen}
              aria-controls="scan-sidebar"
            >
              <span className="drawer-toggle-icon" aria-hidden="true" />
              <span>{drawerOpen ? "收起列表" : "列表／建立掃描"}</span>
            </button>
            <button type="button" className="back-to-list-button" onClick={() => navigate("/scans")}>
              ← 回到掃描列表
            </button>
            <span className="scan-toolbar-spacer" />
            <div className="scan-view-switch" role="group" aria-label="檢視方式">
              <button
                type="button"
                className={`scan-view-tab ${isTopologyPage ? "" : "active"}`}
                aria-pressed={!isTopologyPage}
                onClick={() => navigate(`/scans/${scanId}`)}
              >
                <LayersIcon className="scan-view-icon" />
                報告
              </button>
              <button
                type="button"
                className={`scan-view-tab ${isTopologyPage ? "active" : ""}`}
                aria-pressed={isTopologyPage}
                onClick={() => navigate(`/scans/${scanId}/topology`)}
              >
                <SpiderIcon className="scan-view-icon" />
                拓樸圖
              </button>
            </div>
          </nav>
        )}
        <Outlet context={{ scans, loading }} />
        {!isDetailPage && list}
      </div>
    </div>
  );
}

/** /scans 未選取掃描時的工作台概覽：用列表的真實資料給一行總覽＋下一步提示。 */
function ScansPlaceholder() {
  const context = useOutletContext() || {};
  const scans = context.scans || [];
  const running = scans.filter((scan) => isInProgress(scan.status)).length;
  const scored = scans.filter((scan) => typeof scan.overall_score === "number");
  const average = scored.length
    ? Math.round(scored.reduce((sum, scan) => sum + scan.overall_score, 0) / scored.length)
    : null;
  return (
    <section className="panel scans-overview ag-surface-grid" aria-labelledby="scans-overview-title">
      <ArgusMark size={56} scanning={running > 0} className="scans-overview-mark" />
      <div className="scans-overview-text">
        <p className="ag-eyebrow">掃描工作台</p>
        <h1 className="scans-overview-title" id="scans-overview-title">
          選一個網站，打開它的健檢報告
        </h1>
        <p className="hint-text">點下方任一任務查看互動報告；用「建立授權掃描」表單新增一次掃描。</p>
      </div>
      {scans.length > 0 && (
        <dl className="scans-overview-stats">
          <div>
            <dt>網站</dt>
            <dd className="ag-num">{scans.length}</dd>
          </div>
          <div>
            <dt>進行中</dt>
            <dd className={`ag-num ${running ? "is-live" : ""}`}>{running}</dd>
          </div>
          <div>
            <dt>平均分數</dt>
            <dd className="ag-num">{average ?? "—"}</dd>
          </div>
        </dl>
      )}
    </section>
  );
}

export { ScanLayout, ScansPlaceholder };
