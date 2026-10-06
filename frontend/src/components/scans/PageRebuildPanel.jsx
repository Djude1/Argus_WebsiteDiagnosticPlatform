import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../../api";
import ShareDialog from "../optimize/ShareDialog";
import { ACCESS_OPTIONS } from "../optimize/optimizeLabels";

const POLL_INTERVAL_MS = 5000;
const IN_PROGRESS = new Set(["pending", "snapshotting", "optimizing", "asking"]);

/**
 * 「頁面」分頁每一列的「優化此頁」。
 *
 * 只放決策需要的資訊：會得到什麼、要花多少、進度、成果摘要；完整的前後比較、
 * 修改清單與分享都在成果頁（/scans/:scanId/rebuild/:rebuildId）。
 * 2026-10-06 移除「原樣複刻／下載原樣複刻」：原樣頁面使用者本來就有，沒有實際價值。
 */
function PageRebuildPanel({ scan, page }) {
  const [rebuild, setRebuild] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [pricing, setPricing] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [shareOpen, setShareOpen] = useState(false);
  const cancelledRef = useRef(false);

  const fetchLatest = useCallback(async () => {
    const { data } = await api.get(`/rebuilds/?scan_id=${scan.id}`);
    const rows = Array.isArray(data) ? data : data.results || [];
    return rows.find((row) => String(row.page) === String(page.id)) || null;
  }, [scan.id, page.id]);

  const poll = useCallback(async () => {
    try {
      const latest = await fetchLatest();
      if (cancelledRef.current) return;
      setRebuild(latest);
      setLoaded(true);
      if (latest && IN_PROGRESS.has(latest.status)) setTimeout(poll, POLL_INTERVAL_MS);
    } catch {
      if (!cancelledRef.current) setLoaded(true);
    }
  }, [fetchLatest]);

  useEffect(() => {
    cancelledRef.current = false;
    poll();
    api
      .get("/rebuilds/cost/")
      .then(({ data }) => !cancelledRef.current && setPricing(data))
      .catch(() => {});
    return () => {
      cancelledRef.current = true;
    };
  }, [poll]);

  async function start() {
    setBusy(true);
    setError("");
    try {
      const { data } = await api.post("/rebuilds/", { page: page.id });
      setRebuild(data);
      setTimeout(poll, POLL_INTERVAL_MS);
    } catch (err) {
      setError(err?.response?.data?.detail || "無法開始優化。");
    } finally {
      setBusy(false);
    }
  }

  const resultPath = rebuild ? `/scans/${scan.id}/rebuild/${rebuild.id}` : "";
  const running = rebuild && IN_PROGRESS.has(rebuild.status);
  const done = rebuild && (rebuild.status === "succeeded" || rebuild.status === "asking");
  const result = rebuild?.result_summary || {};
  const costText = pricing ? `預扣 ${pricing.hold} 點，完成後依實際用量結算並退回差額（餘額 ${pricing.balance} 點）` : "";

  if (!loaded) return <p className="opt-muted">載入中…</p>;

  return (
    <div className="opt-row-panel">
      {!rebuild && (
        <>
          <div className="opt-row-intro">
            <p className="opt-row-title">讓 Argus 優化這一頁</p>
            <ul className="opt-row-gains">
              <li>修好這一頁能在 HTML 解決的 SEO、無障礙與效能問題</li>
              <li>改善版面層次、間距、按鈕與行動版，前後差異一眼看得出來</li>
              <li>產生前後對照與修改說明，可以直接分享給設計師或工程師</li>
            </ul>
          </div>
          <div className="opt-row-actions">
            <button type="button" className="primary-button" disabled={busy} onClick={start}>
              {busy ? "建立中…" : "開始優化"}
            </button>
            {costText && <p className="opt-muted">{costText}</p>}
          </div>
        </>
      )}

      {running && (
        <>
          <div className="opt-row-intro">
            <p className="opt-row-title"><span className="opt-progress-dot" aria-hidden="true" />Argus 正在優化這一頁</p>
            <p className="opt-muted">通常需要 1～3 分鐘，可以先離開，完成後這裡會顯示結果。</p>
          </div>
          <div className="opt-row-actions">
            <Link className="secondary-button" to={resultPath}>查看即時進度</Link>
          </div>
        </>
      )}

      {done && (
        <>
          <div className="opt-row-intro">
            <p className="opt-row-title">{result.summary || "優化完成"}</p>
            <p className="opt-row-stats">
              <span>視覺改善 <strong>{result.visual || 0}</strong></span>
              <span>技術修正 <strong>{result.technical || 0}</strong></span>
              <span>可量測改善 <strong>{result.improved || 0}</strong></span>
              {rebuild.share_active && (
                <span className="opt-shared">
                  已分享：{ACCESS_OPTIONS.find((o) => o.value === rebuild.share_access)?.label}
                </span>
              )}
            </p>
          </div>
          <div className="opt-row-actions">
            <Link className="primary-button" to={resultPath}>查看前後對照</Link>
            <button type="button" className="secondary-button" onClick={() => setShareOpen(true)}>分享</button>
            <button type="button" className="opt-text-button" disabled={busy} onClick={start}>重新優化</button>
          </div>
        </>
      )}

      {rebuild?.status === "failed" && (
        <>
          <div className="opt-row-intro">
            <p className="opt-row-title">上次優化沒有完成</p>
            <p className="opt-muted">{rebuild.error || "發生未預期的錯誤。"} 預扣的點數已退回。</p>
          </div>
          <div className="opt-row-actions">
            <button type="button" className="primary-button" disabled={busy} onClick={start}>
              {busy ? "建立中…" : "再試一次"}
            </button>
          </div>
        </>
      )}

      {error && <p className="error-text" role="alert">{error}</p>}
      {shareOpen && rebuild && (
        <ShareDialog rebuild={rebuild} onChange={setRebuild} onClose={() => setShareOpen(false)} />
      )}
    </div>
  );
}

export default PageRebuildPanel;
