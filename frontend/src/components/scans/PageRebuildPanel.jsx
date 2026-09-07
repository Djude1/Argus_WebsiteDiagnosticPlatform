import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../api";

const POLL_INTERVAL_MS = 5000;

// 後端 SiteRebuild.Status 的對應。進行中的三個狀態要繼續 polling。
const IN_PROGRESS = new Set(["pending", "snapshotting", "optimizing"]);
const STATUS_LABEL = {
  pending: "排隊中",
  snapshotting: "複刻中",
  optimizing: "優化中",
  succeeded: "完成",
  failed: "未完成",
};

/**
 * 單一頁面的「網頁複刻與優化」。
 *
 * 複刻與優化是兩段成本完全不同的產出，UI 上必須分開呈現：優化失敗時複刻
 * 通常仍在，使用者還是拿得到原樣快照。把兩者併成一個「下載」按鈕會讓人
 * 以為整件事都失敗了。
 */
function PageRebuildPanel({ scan, page }) {
  const [rebuild, setRebuild] = useState(null);
  const [pricing, setPricing] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // 換頁籤時舊的 polling 要停掉，否則會把前一頁的結果寫進當前狀態
  const cancelledRef = useRef(false);

  const fetchLatest = useCallback(async () => {
    const { data } = await api.get(`/rebuilds/?scan_id=${scan.id}`);
    const rows = Array.isArray(data) ? data : data.results || [];
    // 後端已依 -created_at 排序，同一頁取最新那筆
    return rows.find((row) => String(row.page) === String(page.id)) || null;
  }, [scan.id, page.id]);

  useEffect(() => {
    cancelledRef.current = false;
    let timer = null;

    async function poll() {
      try {
        const latest = await fetchLatest();
        if (cancelledRef.current) return;
        setRebuild(latest);
        if (latest && IN_PROGRESS.has(latest.status)) {
          timer = setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch {
        // 暫時失敗不清空畫面，下一次使用者操作會再拉
      }
    }
    poll();

    // 價格與餘額：按鈕要先說清楚代價，不能讓使用者按下去才吃 402
    api
      .get("/rebuilds/cost/")
      .then(({ data }) => {
        if (!cancelledRef.current) setPricing(data);
      })
      .catch(() => {
        // 拿不到就不顯示價格，功能本身不受影響
      });

    return () => {
      cancelledRef.current = true;
      if (timer) clearTimeout(timer);
    };
  }, [fetchLatest]);

  async function handleGenerate() {
    setBusy(true);
    setError("");
    try {
      const { data } = await api.post("/rebuilds/", { page: page.id });
      setRebuild(data);
      // 立刻進入 polling：任務是非同步的，POST 回來時還沒開始跑
      const tick = async () => {
        if (cancelledRef.current) return;
        const latest = await fetchLatest();
        if (cancelledRef.current) return;
        setRebuild(latest);
        if (latest && IN_PROGRESS.has(latest.status)) {
          setTimeout(tick, POLL_INTERVAL_MS);
        }
      };
      setTimeout(tick, POLL_INTERVAL_MS);
    } catch (err) {
      setError(err?.response?.data?.detail || "無法建立複刻任務。");
    } finally {
      setBusy(false);
    }
  }

  async function download(variant) {
    setError("");
    try {
      const response = await api.get(
        `/rebuilds/${rebuild.id}/download/?variant=${variant}`,
        { responseType: "blob" },
      );
      const url = URL.createObjectURL(response.data);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `argus-scan-${scan.id}-page-${page.id}-${variant}.html`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("下載失敗，檔案可能已被清理。");
    }
  }

  const running = rebuild && IN_PROGRESS.has(rebuild.status);

  return (
    <div className="rebuild-box">
      <p className="rebuild-title">🧬 網頁複刻與優化</p>
      <p className="rebuild-desc">
        複刻這一頁的原始樣貌，並依本頁的診斷結果產生優化版本。
        {pricing && `每次消耗 ${pricing.cost} 點，目前餘額 ${pricing.balance} 點。`}
      </p>

      {!rebuild && (
        <button
          className="secondary-button rebuild-action"
          type="button"
          disabled={busy}
          onClick={handleGenerate}
        >
          {busy
            ? "建立中…"
            : pricing
              ? `產生複刻與優化版（${pricing.cost} 點）`
              : "產生複刻與優化版"}
        </button>
      )}

      {rebuild && (
        <>
          <p className="rebuild-status">
            <span className={`rebuild-dot status-${rebuild.status}`} />
            {STATUS_LABEL[rebuild.status] || rebuild.status}
            {running && "…"}
          </p>

          {rebuild.error && <p className="rebuild-note">{rebuild.error}</p>}

          {rebuild.has_snapshot && (
            <button
              className="secondary-button rebuild-action"
              type="button"
              onClick={() => download("original")}
            >
              下載原樣複刻
            </button>
          )}
          {rebuild.has_optimized && (
            <button
              className="secondary-button rebuild-action"
              type="button"
              onClick={() => download("optimized")}
            >
              下載優化版
            </button>
          )}
          {!running && (
            <button
              className="rebuild-retry"
              type="button"
              disabled={busy}
              onClick={handleGenerate}
            >
              重新產生
            </button>
          )}
        </>
      )}

      {error && <p className="rebuild-note error">{error}</p>}
      <p className="rebuild-note">
        下載的是 HTML 檔，內容來自受測網站，開啟前請自行確認來源。
      </p>
    </div>
  );
}

export default PageRebuildPanel;
