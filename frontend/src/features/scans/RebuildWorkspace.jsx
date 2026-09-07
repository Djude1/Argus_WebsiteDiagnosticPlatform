import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../../api";

// 專屬頁面比側欄面板更新得快：這裡是使用者盯著看的畫面，5 秒一跳會很鈍。
const POLL_INTERVAL_MS = 1000;

const IN_PROGRESS = new Set(["pending", "snapshotting", "optimizing", "asking"]);
const STATUS_LABEL = {
  pending: "排隊中",
  snapshotting: "複刻中",
  optimizing: "優化中",
  asking: "回答中",
  succeeded: "完成",
  failed: "未完成",
};
// 進行中要讓使用者知道「它現在在做什麼」，而不只是「還在跑」。
// 這是照 AI-Wealth-Manager 的做法：狀態列 + 經過秒數 + 工具呼叫次數。
function currentAction(rebuild) {
  if (rebuild.status === "snapshotting") return "複刻原始頁面…";
  if (rebuild.status === "asking") return "思考中…";
  if (rebuild.status !== "optimizing") return "";
  const lastTool = [...(rebuild.trace || [])].reverse().find((e) => e.kind === "tool");
  return lastTool ? `執行 ${lastTool.text}…` : "分析診斷結果…";
}

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
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const traceEndRef = useRef(null);
  const traceBodyRef = useRef(null);
  const cancelledRef = useRef(false);
  const startedAtRef = useRef(0);

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

  // 經過秒數：沒有這個，跑久了分不出「還在想」與「卡住」
  useEffect(() => {
    if (!running) return undefined;
    if (!startedAtRef.current) startedAtRef.current = Date.now();
    const timer = setInterval(
      () => setElapsed(Math.round((Date.now() - startedAtRef.current) / 1000)),
      1000,
    );
    return () => clearInterval(timer);
  }, [running]);

  useEffect(() => {
    if (!running) startedAtRef.current = 0;
  }, [running]);

  // 自動捲到最新——但**只在使用者沒有往上捲去讀的時候**。
  // 無條件捲動會把正在讀舊內容的人一直拉回底部。
  useEffect(() => {
    if (!running) return;
    const body = traceBodyRef.current;
    if (!body) return;
    const pinned = body.scrollHeight - body.scrollTop - body.clientHeight < 40;
    if (pinned) traceEndRef.current?.scrollIntoView({ block: "end" });
  }, [rebuild?.trace?.length, rebuild?.reply, running]);

  async function submitQuestion(event) {
    event.preventDefault();
    const text = question.trim();
    if (!text || asking) return;
    setAsking(true);
    setError("");
    try {
      await api.post(`/rebuilds/${rebuildId}/ask/`, { question: text });
      setQuestion("");
      // 立刻重新 polling：任務是非同步的，狀態要靠下一次讀取才會變
      const { data } = await api.get(`/rebuilds/${rebuildId}/`);
      setRebuild(data);
    } catch (err) {
      setError(err?.response?.data?.detail || "無法送出問題。");
    } finally {
      setAsking(false);
    }
  }

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

  const toolCount = (rebuild.trace || []).filter((e) => e.kind === "tool").length;
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
          <div className={`rebuild-ws-live ${running ? "is-live" : "is-done"}`}>
            <span className="rebuild-ws-live-dot" />
            <span>{running ? currentAction(rebuild) || "進行中…" : "已結束"}</span>
            <span className="rebuild-ws-live-meta">
              {toolCount > 0 && `${toolCount} 次工具呼叫`}
              {running && ` · ${elapsed}s`}
            </span>
          </div>

          <details className="rebuild-ws-trace-wrap" open>
            <summary>思考過程與工具呼叫</summary>
            {/* 等寬、淡色、連續流動——這是過程不是結論，視覺權重要低於下方的回覆 */}
            <div className="rebuild-ws-trace" ref={traceBodyRef}>
              {(rebuild.trace || []).map((entry, index) =>
                entry.kind === "tool" ? (
                  <span className="rebuild-ws-tool" key={`t-${index}`}>
                    ▸ {entry.text}
                  </span>
                ) : (
                  <span className="rebuild-ws-think" key={`k-${index}`}>
                    {entry.text}
                  </span>
                ),
              )}
              {!(rebuild.trace || []).length && (
                <span className="hint-text">
                  {running ? "等待 agent 開始…" : "這次沒有記錄到過程。"}
                </span>
              )}
              <div ref={traceEndRef} />
            </div>
          </details>

          {/* 回覆是結論，必須跟過程分開、字級正常。混在推理片段裡會找不到重點 */}
          <div className="rebuild-ws-reply-head">Agent 回覆</div>
          <div className="rebuild-ws-reply">
            {rebuild.reply || (running ? "…" : "（這一輪沒有文字回覆）")}
          </div>

          {(rebuild.conversation || []).length > 0 && (
            <div className="rebuild-ws-chat">
              {rebuild.conversation.map((turn, index) => (
                <p className={`rebuild-ws-turn role-${turn.role}`} key={`c-${index}`}>
                  <span className="rebuild-ws-turn-tag">
                    {turn.role === "user" ? "你" : "Agent"}
                  </span>
                  {turn.text}
                </p>
              ))}
            </div>
          )}

          <form className="rebuild-ws-ask" onSubmit={submitQuestion}>
            <textarea
              className="input rebuild-ws-ask-input"
              placeholder="追問或要求更深入的優化，例如：為什麼沒有補圖片的 alt？"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              disabled={running || asking}
              rows={2}
            />
            <button
              className="secondary-button"
              type="submit"
              disabled={running || asking || !question.trim()}
            >
              {asking ? "送出中…" : "送出"}
            </button>
          </form>
          <p className="rebuild-ws-ask-note">
            追問會延續同一個對話（agent 記得這一頁的 HTML 與診斷結果），依實際用量計費。
          </p>
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

          {rebuild.edit_report?.length > 0 && (
            <div className="rebuild-ws-edits">
              <p className="rebuild-ws-edits-title">
                套用的修改（{rebuild.edit_report.filter((e) => e.applied).length}/
                {rebuild.edit_report.length}）
              </p>
              {rebuild.edit_report.map((item, index) => (
                <p
                  className={`rebuild-ws-edit ${item.applied ? "ok" : "miss"}`}
                  key={`edit-${index}`}
                >
                  <span className="rebuild-ws-edit-count">
                    {item.applied ? `×${item.applied}` : "未套用"}
                  </span>
                  {item.why || item.find}
                </p>
              ))}
            </div>
          )}

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
