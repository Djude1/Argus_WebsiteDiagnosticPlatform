import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../../api";

// 專屬頁面比側欄面板更新得快：這裡是使用者盯著看的畫面，5 秒一跳會很鈍。
const POLL_INTERVAL_MS = 1000;

const IN_PROGRESS = new Set(["pending", "snapshotting", "optimizing"]);
const STATUS_LABEL = {
  pending: "排隊中",
  snapshotting: "複刻中",
  optimizing: "優化中",
  succeeded: "完成",
  failed: "未完成",
};
const TRACE_LABEL = { thinking: "推理", tool: "工具", text: "回覆" };

/**
 * 單次複刻的完整工作區：左側 AI 思考過程、右側產出預覽。
 *
 * 之所以要獨立成一頁而不是留在掃描詳情的側欄：思考流是需要「閱讀」的內容，
 * 塞在 360px 的欄位裡與 Top Actions、篩選器搶空間，看不了幾個字。
 */
function RebuildWorkspace() {
  const { scanId, rebuildId } = useParams();
  const navigate = useNavigate();
  const [rebuild, setRebuild] = useState(null);
  const [variant, setVariant] = useState("optimized");
  const [docs, setDocs] = useState({});
  const [error, setError] = useState("");
  const traceEndRef = useRef(null);
  const cancelledRef = useRef(false);

  const running = rebuild && IN_PROGRESS.has(rebuild.status);

  useEffect(() => {
    cancelledRef.current = false;
    let timer = null;
    async function poll() {
      try {
        const { data } = await api.get(`/rebuilds/${rebuildId}/`);
        if (cancelledRef.current) return;
        setRebuild(data);
        if (IN_PROGRESS.has(data.status)) {
          timer = setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch {
        if (!cancelledRef.current) setError("無法載入這次複刻，可能不存在或無權限。");
      }
    }
    poll();
    return () => {
      cancelledRef.current = true;
      if (timer) clearTimeout(timer);
    };
  }, [rebuildId]);

  // 跑的時候讓思考流自動捲到最新一則，不然使用者得一直手動往下拉
  useEffect(() => {
    if (running) traceEndRef.current?.scrollIntoView({ block: "end" });
  }, [rebuild?.trace?.length, running]);

  const loadDoc = useCallback(
    async (which) => {
      if (docs[which] !== undefined) return;
      try {
        const response = await api.get(
          `/rebuilds/${rebuildId}/download/?variant=${which}`,
          { responseType: "text" },
        );
        setDocs((prev) => ({ ...prev, [which]: response.data }));
      } catch {
        setDocs((prev) => ({ ...prev, [which]: null }));
      }
    },
    [rebuildId, docs],
  );

  useEffect(() => {
    if (!rebuild) return;
    if (variant === "optimized" && rebuild.has_optimized) loadDoc("optimized");
    if (variant === "original" && rebuild.has_snapshot) loadDoc("original");
  }, [rebuild, variant, loadDoc]);

  // 完成後兩份都拉回來，才能回答「到底有沒有改到東西」
  useEffect(() => {
    if (rebuild?.has_optimized && rebuild?.has_snapshot) {
      loadDoc("original");
      loadDoc("optimized");
    }
  }, [rebuild?.has_optimized, rebuild?.has_snapshot, loadDoc]);

  function download(which) {
    const html = docs[which];
    if (!html) return;
    const url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `argus-rebuild-${rebuildId}-${which}.html`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  if (error) {
    return (
      <section className="panel">
        <p className="error-text">{error}</p>
        <button className="secondary-button mt-3" type="button" onClick={() => navigate(`/scans/${scanId}`)}>
          回到掃描結果
        </button>
      </section>
    );
  }
  if (!rebuild) {
    return (
      <section className="panel">
        <p className="hint-text">載入中...</p>
      </section>
    );
  }

  const both = docs.original != null && docs.optimized != null;
  const identical = both && docs.original === docs.optimized;
  const current = docs[variant];

  return (
    <section className="rebuild-workspace">
      <div className="rebuild-ws-head">
        <button className="rebuild-ws-back" type="button" onClick={() => navigate(`/scans/${scanId}`)}>
          ← 回到掃描結果
        </button>
        <h2 className="rebuild-ws-title">🧬 網頁複刻與優化</h2>
        <p className="rebuild-ws-url">{rebuild.page_url}</p>
        <p className="rebuild-ws-status">
          <span className={`rebuild-dot status-${rebuild.status}`} />
          {STATUS_LABEL[rebuild.status] || rebuild.status}
          {running && "…"}
          {rebuild.coins_charged > 0 && `　實際扣 ${rebuild.coins_charged} 點`}
        </p>
        {rebuild.error && <p className="error-text mt-2">{rebuild.error}</p>}
      </div>

      <div className="rebuild-ws-grid">
        <div className="rebuild-ws-pane">
          <h3 className="rebuild-ws-pane-title">AI 思考過程</h3>
          <div className="rebuild-ws-trace">
            {(rebuild.trace || []).map((entry, index) => (
              <div className={`rebuild-ws-entry kind-${entry.kind}`} key={`${entry.kind}-${index}`}>
                <span className="rebuild-ws-entry-tag">{TRACE_LABEL[entry.kind] || entry.kind}</span>
                <p className="rebuild-ws-entry-text">{entry.text}</p>
              </div>
            ))}
            {!(rebuild.trace || []).length && (
              <p className="hint-text">{running ? "等待 agent 開始…" : "這次沒有記錄到過程。"}</p>
            )}
            <div ref={traceEndRef} />
          </div>
        </div>

        <div className="rebuild-ws-pane">
          <div className="rebuild-ws-pane-head">
            <h3 className="rebuild-ws-pane-title">產出預覽</h3>
            <div className="rebuild-ws-tabs">
              <button
                className={`rebuild-ws-tab ${variant === "original" ? "active" : ""}`}
                type="button"
                onClick={() => setVariant("original")}
                disabled={!rebuild.has_snapshot}
              >
                原樣複刻
              </button>
              <button
                className={`rebuild-ws-tab ${variant === "optimized" ? "active" : ""}`}
                type="button"
                onClick={() => setVariant("optimized")}
                disabled={!rebuild.has_optimized}
              >
                優化版
              </button>
            </div>
          </div>

          {both && (
            <p className={`rebuild-ws-diff ${identical ? "same" : "changed"}`}>
              {identical
                ? "⚠ 兩份內容完全相同——agent 沒有改動任何東西"
                : `已改動：原稿 ${docs.original.length.toLocaleString()} → 優化版 ${docs.optimized.length.toLocaleString()} 字元`}
            </p>
          )}

          {current ? (
            // sandbox 不加任何 allow-*：這份 HTML 來自受測網站，必須讓它
            // 在獨立的 opaque origin 裡、且完全不執行 script。
            <iframe className="rebuild-ws-frame" title="產出預覽" sandbox="" srcDoc={current} />
          ) : (
            <p className="hint-text">{running ? "產出後顯示。" : "此版本尚未產出。"}</p>
          )}

          <div className="rebuild-ws-actions">
            <button className="secondary-button" type="button" onClick={() => download("original")} disabled={!docs.original}>
              下載原樣複刻
            </button>
            <button className="secondary-button" type="button" onClick={() => download("optimized")} disabled={!docs.optimized}>
              下載優化版
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

export { RebuildWorkspace };
