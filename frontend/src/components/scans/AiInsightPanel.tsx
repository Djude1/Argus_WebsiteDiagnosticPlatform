import { useEffect, useState } from "react";

import { api } from "../../api";

// AI 掃描解讀（scan.ai_insight，後端 apps/scans/ai_insight.py）：整體診斷、優先處理建議、
// 高風險問題的 AI 複核。AI 產生、只供參考：不改嚴重度、不影響分數，畫面上一律標明。
// 掃描完成時不自動產生（每次都花 token，2026-10-10 起改為使用者按「產生 AI 解讀」才派工）；
// 產生中顯示 Thought Spark 動畫並每 5 秒重新讀取，直到完成或失敗；失敗時可重新產生。

const POLL_MS = 5000;

// 後端 JSONField，schema 只能是 unknown；結構見 apps/scans/ai_insight.py
type Verdict = "likely_valid" | "possible_false_positive" | "needs_check";
type AiPriority = { title: string; why?: string; how?: string; rule_ids?: string[] };
type AiTriage = { rule_id: string; title?: string; verdict: Verdict; label: string; reason?: string };
type AiInsight = {
  status?: "ready" | "generating" | "failed";
  summary?: string;
  reason?: string;
  priorities?: AiPriority[];
  triage?: AiTriage[];
};
type ScanLike = { id: number; status: string; is_demo?: boolean; ai_insight?: unknown };
type FindingLike = { rule_id?: string | null; title?: string };

const VERDICT_TONE: Record<Verdict, string> = {
  likely_valid: "is-bad",
  possible_false_positive: "is-good",
  needs_check: "is-warn",
};

// 產生中的步驟文字（每 STEP_MS 前進一格，停在最後一格直到完成）
const WATCH_STEPS = ["讀取這次的問題與證據", "複核高風險問題是否可能誤報", "整理整體診斷與優先順序"];
const STEP_MS = 6000;
/**
 * AI 解讀產生中的動畫：Argus Minimal Loading Pack「08 · Thought Spark」原樣使用，
 * 下方保留原檔的「AI Agent 正在分析…」（2026-10-10 使用者指定不改）。
 * 右側另列目前步驟與已等待秒數（92-layout.css）。
 */
function AiThinkingLoader() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, []);
  const step = Math.min(Math.floor((elapsed * 1000) / STEP_MS), WATCH_STEPS.length - 1);
  return (
    <div className="ai-watch" role="status" aria-live="polite">
      <div className="ai-spark-stage">
        <div className="ag-spark" aria-hidden="true" />
        <div className="ag-loader-label">AI Agent 正在分析…</div>
      </div>
      <div className="ai-watch-copy">
        <ol className="ai-watch-steps">
          {WATCH_STEPS.map((label, idx) => (
            <li
              key={label}
              className={idx < step ? "is-done" : idx === step ? "is-active" : ""}
              aria-current={idx === step ? "step" : undefined}
            >
              {label}
            </li>
          ))}
        </ol>
        <p className="ai-insight-note">
          已等待 {elapsed} 秒。通常需要 30 秒到 1 分鐘，完成後會自動顯示；可以先看下方的問題清單。
        </p>
      </div>
    </div>
  );
}

/** 依規則代號找出這次掃描的問題標題（優先處理的連結文字用）。 */
function ruleTitle(findings: FindingLike[], ruleId: string) {
  return findings.find((f) => f.rule_id === ruleId)?.title || ruleId;
}

function AiInsightPanel({
  scan,
  findings = [],
  onInsightChange,
  onSelectRule,
}: {
  scan: ScanLike;
  findings?: FindingLike[];
  onInsightChange?: (insight: AiInsight) => void;
  onSelectRule?: (ruleId: string) => void;
}) {
  const [insight, setInsight] = useState<AiInsight>((scan.ai_insight as AiInsight) || {});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const status = insight?.status;
  const priorities = insight.priorities ?? [];
  const triage = insight.triage ?? [];

  useEffect(() => {
    setInsight((scan.ai_insight as AiInsight) || {});
  }, [scan.id, scan.ai_insight]);

  useEffect(() => {
    onInsightChange?.(insight);
  }, [insight, onInsightChange]);

  useEffect(() => {
    if (status !== "generating") return undefined;
    let cancelled = false;
    const timer = setInterval(async () => {
      try {
        const response = await api.get(`/scans/${scan.id}/`);
        if (!cancelled) setInsight((response.data.ai_insight as AiInsight) || {});
      } catch {
        // 讀取失敗下一輪再試
      }
    }, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [status, scan.id]);

  if (scan.status !== "completed" || (scan.is_demo && !status)) return null;

  async function regenerate() {
    setBusy(true);
    setError("");
    try {
      const response = await api.post(`/scans/${scan.id}/ai-insight/`);
      setInsight((response.data.ai_insight as AiInsight) || {});
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || "無法產生 AI 解讀，請稍後再試。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel ai-insight" aria-labelledby="ai-insight-title">
      <header className="ai-insight-header">
        <h2 id="ai-insight-title" className="ai-insight-title">AI 解讀</h2>
        <span className="ai-insight-tag">AI 產生，僅供參考，不影響分數</span>
      </header>

      {(status === "generating" || busy) && <AiThinkingLoader />}

      {(!status || status === "failed") && !busy && (
        <div className="ai-insight-empty">
          <p className="ai-insight-note">
            {status === "failed"
              ? `這次沒有產生成功：${insight.reason || "原因不明"}`
              : "需要時再產生：讓 AI 讀完這次的問題與證據，寫一段整體診斷，並複核高風險問題是否可能誤報。"}
          </p>
          <button className="primary-button" type="button" onClick={regenerate}>
            {status === "failed" ? "重新產生" : "產生 AI 解讀"}
          </button>
          {error && <p className="error-text">{error}</p>}
        </div>
      )}

      {status === "ready" && (
        <>
          <p className="ai-insight-summary">{insight.summary}</p>

          {priorities.length > 0 && (
            <>
              <h3 className="ai-insight-subtitle">建議先處理</h3>
              <ol className="ai-insight-priorities">
                {priorities.map((item, idx) => (
                  <li key={`${item.title}-${idx}`} className="ai-insight-priority">
                    <p className="ai-insight-priority-title">{item.title}</p>
                    {item.why && <p className="ai-insight-text"><strong>為什麼：</strong>{item.why}</p>}
                    {item.how && <p className="ai-insight-text"><strong>怎麼做：</strong>{item.how}</p>}
                    {(item.rule_ids ?? []).length > 0 && (
                      <p className="ai-insight-links">
                        相關問題：
                        {(item.rule_ids ?? []).map((ruleId) => (
                          <button
                            key={ruleId}
                            className="ai-insight-link"
                            type="button"
                            onClick={() => onSelectRule?.(ruleId)}
                          >
                            {ruleTitle(findings, ruleId)}
                          </button>
                        ))}
                      </p>
                    )}
                  </li>
                ))}
              </ol>
            </>
          )}

          {triage.length > 0 && (
            <>
              <h3 className="ai-insight-subtitle">AI 複核高風險問題</h3>
              <p className="ai-insight-note">AI 看過證據後的判斷；問題的嚴重度不會因此改變，請由網站管理者確認。</p>
              <ul className="ai-insight-triage">
                {triage.map((item) => (
                  <li key={item.rule_id} className="ai-insight-triage-row">
                    <span className={`ai-verdict ${VERDICT_TONE[item.verdict] || ""}`}>{item.label}</span>
                    <button className="ai-insight-link" type="button" onClick={() => onSelectRule?.(item.rule_id)}>
                      {item.title || ruleTitle(findings, item.rule_id)}
                    </button>
                    {item.reason && <span className="ai-insight-text">{item.reason}</span>}
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </section>
  );
}

/** 選中問題的 AI 複核結果（問題詳情內一行）；沒有複核就不顯示。 */
function AiTriageNote({ insight, finding }: { insight: AiInsight | null; finding: FindingLike | null }) {
  const item = insight?.triage?.find((t) => t.rule_id === finding?.rule_id);
  if (!item) return null;
  return (
    <p className="ai-triage-note">
      <span className={`ai-verdict ${VERDICT_TONE[item.verdict] || ""}`}>AI 複核：{item.label}</span>
      {item.reason && <span>{item.reason}</span>}
    </p>
  );
}

export { AiInsightPanel, AiTriageNote };
export type { AiInsight };
