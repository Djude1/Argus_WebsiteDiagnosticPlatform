import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useOutletContext, useParams } from "react-router-dom";

import { api } from "../../api";
import OptimizationReport from "../../components/optimize/OptimizationReport";
import ShareDialog from "../../components/optimize/ShareDialog";
import { ACCESS_OPTIONS } from "../../components/optimize/optimizeLabels";
import { formatDateTime } from "../../shared/formatters";

const POLL_INTERVAL_MS = 1500;
const IN_PROGRESS = new Set(["pending", "snapshotting", "optimizing", "asking"]);
// 送出追問後 worker 還沒撿起任務前，狀態仍是 succeeded；寬限期內繼續 polling
const START_GRACE_POLLS = 20;
const STATUS_LABEL = {
  pending: "排隊中",
  snapshotting: "讀取頁面",
  optimizing: "Argus 正在優化",
  asking: "回答追問中",
  succeeded: "已完成",
  failed: "未完成",
};

function currentAction(rebuild) {
  if (rebuild.status === "pending") return "等待開始…";
  if (rebuild.status === "snapshotting") return "讀取掃描時保存的頁面…";
  if (rebuild.status === "asking") return "思考中…";
  const lastTool = [...(rebuild.trace || [])].reverse().find((e) => e.kind === "tool");
  return lastTool ? `執行 ${lastTool.text}…` : "分析診斷結果與頁面結構…";
}

function TraceEntries({ entries }) {
  return entries.map((entry, index) =>
    entry.kind === "tool" ? (
      <span className="opt-trace-tool" key={`t-${index}`}>▸ {entry.text}</span>
    ) : (
      <span className="opt-trace-think" key={`k-${index}`}>{entry.text}</span>
    ),
  );
}

/** 已結束那幾輪的思考流：展開才抓（detail 每秒 polling，不能夾帶歷史思考流）。 */
function TurnTrace({ rebuildId, index }) {
  const [entries, setEntries] = useState(null);
  const [failed, setFailed] = useState(false);
  async function loadOnce(event) {
    if (!event.currentTarget.open || entries) return;
    try {
      const { data } = await api.get(`/rebuilds/${rebuildId}/turn-trace/?index=${index}`);
      setEntries(data.trace || []);
    } catch {
      setFailed(true);
    }
  }
  return (
    <details className="opt-trace" onToggle={loadOnce}>
      <summary>思考過程</summary>
      <div className="opt-trace-body">
        {failed && <span className="opt-muted">載入失敗，重新展開可再試一次。</span>}
        {entries && !entries.length && <span className="opt-muted">這一輪沒有記錄到過程。</span>}
        {entries && <TraceEntries entries={entries} />}
      </div>
    </details>
  );
}

/** AI 的說明、過程與追問（審查用，預設收合；成果本身在上方報告）。 */
function AgentThread({ rebuild, running, onAsk }) {
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState("");
  const thread = rebuild.conversation || [];

  async function submit(event) {
    event.preventDefault();
    const text = question.trim();
    if (!text || asking) return;
    setAsking(true);
    setError("");
    try {
      await api.post(`/rebuilds/${rebuild.id}/ask/`, { question: text });
      setQuestion("");
      onAsk();
    } catch (err) {
      setError(err?.response?.data?.detail || "無法送出問題。");
    } finally {
      setAsking(false);
    }
  }

  return (
    <details className="opt-agent" open={running || undefined}>
      <summary>AI 說明、過程與追問</summary>
      <div className="opt-agent-body">
        {thread.length ? (
          thread.map((turn, index) =>
            turn.role === "user" ? (
              <p className="opt-turn is-user" key={index}><span>你</span>{turn.text}</p>
            ) : (
              <div key={index}>
                {turn.has_trace && <TurnTrace rebuildId={rebuild.id} index={index} />}
                <p className="opt-turn is-agent"><span>Argus</span>{turn.text}</p>
              </div>
            ),
          )
        ) : (
          <p className="opt-turn is-agent"><span>Argus</span>{rebuild.reply || (running ? "…" : "（沒有文字說明）")}</p>
        )}
        {running && (rebuild.trace || []).length > 0 && (
          <details className="opt-trace" open>
            <summary>目前的思考過程</summary>
            <div className="opt-trace-body"><TraceEntries entries={rebuild.trace} /></div>
          </details>
        )}
        <form className="opt-ask" onSubmit={submit}>
          <textarea
            className="input"
            rows={2}
            placeholder="追問或要求進一步優化，例如：手機版的導覽列還能怎麼改？"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            disabled={running || asking}
          />
          <button className="secondary-button" type="submit" disabled={running || asking || !question.trim()}>
            {asking ? "送出中…" : "送出追問"}
          </button>
        </form>
        {error && <p className="error-text" role="alert">{error}</p>}
        <p className="opt-muted">追問會延續同一段對話（Argus 記得這一頁的內容與診斷），依實際用量計費。</p>
      </div>
    </details>
  );
}

/**
 * /scans/:scanId/rebuild/:rebuildId：一次頁面優化的成果頁（擁有者）。
 * 這是 Argus 的成果展示頁：前後比較、修改了什麼、改善多少，並可分享給設計師與工程師。
 */
function OptimizationResultPage() {
  const { scanId, rebuildId } = useParams();
  const { project } = useOutletContext() || {};
  const navigate = useNavigate();
  const [rebuild, setRebuild] = useState(null);
  const [error, setError] = useState("");
  const [shareOpen, setShareOpen] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [pollNonce, setPollNonce] = useState(0);
  const waitingStartRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    let timer = null;
    async function poll(attempt) {
      try {
        const { data } = await api.get(`/rebuilds/${rebuildId}/`);
        if (cancelled) return;
        setRebuild(data);
        const inProgress = IN_PROGRESS.has(data.status);
        if (inProgress) waitingStartRef.current = false;
        if (inProgress || (waitingStartRef.current && attempt < START_GRACE_POLLS)) {
          timer = setTimeout(() => poll(attempt + 1), POLL_INTERVAL_MS);
        }
      } catch {
        if (!cancelled) setError("無法載入這次優化，可能不存在或無權限。");
      }
    }
    poll(0);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [rebuildId, pollNonce]);

  const loadHtml = useCallback(
    (variant) =>
      api
        .get(`/rebuilds/${rebuildId}/download/?variant=${variant}`, { responseType: "text" })
        .then((response) => response.data),
    [rebuildId],
  );

  async function downloadOptimized() {
    const html = await loadHtml("optimized");
    const url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `argus-optimized-page-${rebuild.page}.html`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function regenerate() {
    setRegenerating(true);
    try {
      const { data } = await api.post("/rebuilds/", { page: rebuild.page });
      setRegenerating(false);
      navigate(`/scans/${scanId}/rebuild/${data.id}`);
    } catch (err) {
      setError(err?.response?.data?.detail || "無法重新優化。");
      setRegenerating(false);
    }
  }

  const backTo = project ? `/projects/${project.id}/pages?scan=${scanId}` : `/scans/${scanId}`;
  if (error && !rebuild) {
    return (
      <section className="panel">
        <p className="error-text">{error}</p>
        <Link className="opt-back" to={backTo}>← 回到頁面列表</Link>
      </section>
    );
  }
  if (!rebuild) return <section className="panel"><p className="hint-text">載入中…</p></section>;

  const running = IN_PROGRESS.has(rebuild.status) && rebuild.status !== "asking";
  const done = rebuild.status === "succeeded" || rebuild.status === "asking";
  const shareLabel = rebuild.share_active
    ? ACCESS_OPTIONS.find((o) => o.value === rebuild.share_access)?.label
    : "";

  return (
    <div className="opt-page">
      <header className="opt-head">
        <Link className="opt-back" to={backTo}>← 回到頁面列表</Link>
        <div className="opt-head-row">
          <div className="opt-head-text">
            <p className="opt-eyebrow">頁面優化結果</p>
            <h1 className="opt-title">{rebuild.page_url}</h1>
            <p className="opt-meta">
              <span className={`opt-status is-${rebuild.status}`}>{STATUS_LABEL[rebuild.status] || rebuild.status}</span>
              {formatDateTime(rebuild.created_at)}
              {rebuild.coins_charged > 0 && `・實際使用 ${rebuild.coins_charged} 點`}
              {shareLabel && <span className="opt-shared">已分享：{shareLabel}</span>}
            </p>
          </div>
          {done && (
            <div className="opt-head-actions">
              <button type="button" className="primary-button" onClick={() => setShareOpen(true)}>分享</button>
              <button type="button" className="secondary-button" onClick={downloadOptimized}>下載優化版 HTML</button>
              <button type="button" className="opt-text-button" disabled={regenerating} onClick={regenerate}>
                {regenerating ? "建立中…" : "重新優化"}
              </button>
            </div>
          )}
        </div>
      </header>

      {running && (
        <section className="opt-progress" aria-live="polite">
          <span className="opt-progress-dot" aria-hidden="true" />
          <div>
            <p className="opt-progress-title">{STATUS_LABEL[rebuild.status]}</p>
            <p className="opt-muted">{currentAction(rebuild)} 通常需要 1～3 分鐘，可以先離開，完成後回到「頁面」分頁查看。</p>
          </div>
        </section>
      )}

      {rebuild.status === "failed" && (
        <section className="opt-failed">
          <p className="opt-progress-title">這次優化沒有完成</p>
          <p className="opt-muted">{rebuild.error || "發生未預期的錯誤。"} 預扣的點數已全數退回。</p>
          <button type="button" className="primary-button" disabled={regenerating} onClick={regenerate}>
            {regenerating ? "建立中…" : "再試一次"}
          </button>
        </section>
      )}

      {done && rebuild.has_optimized && (
        <OptimizationReport
          loadHtml={loadHtml}
          data={{
            edits: rebuild.edit_report,
            outcome: rebuild.outcome,
            findings: rebuild.findings,
            has_original: rebuild.has_snapshot,
            has_optimized: rebuild.has_optimized,
          }}
        />
      )}

      {(done || running) && (
        <AgentThread
          rebuild={rebuild}
          running={IN_PROGRESS.has(rebuild.status)}
          onAsk={() => {
            waitingStartRef.current = true;
            setPollNonce((n) => n + 1);
          }}
        />
      )}

      {shareOpen && (
        <ShareDialog
          rebuild={rebuild}
          // 分享 API 回的是列表欄位，合併進來，不能蓋掉 edit_report 等詳細資料
          onChange={(updated) => setRebuild((prev) => ({ ...prev, ...updated }))}
          onClose={() => setShareOpen(false)}
        />
      )}
    </div>
  );
}

export { OptimizationResultPage };
