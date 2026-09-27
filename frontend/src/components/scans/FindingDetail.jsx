import { useEffect, useRef, useState } from "react";

import { CATEGORY_LABELS, SEVERITY_LABEL } from "../../shared/AppShared.jsx";

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

/** 複製按鈕：成功後 2 秒顯示「已複製」，失敗提示手動選取。 */
function CopyButton({ text, label, copiedLabel = "已複製 ✓", className = "secondary-button" }) {
  const [state, setState] = useState("idle"); // idle | copied | failed
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);

  async function handleClick() {
    try {
      await navigator.clipboard.writeText(text || "");
      setState("copied");
    } catch {
      setState("failed");
    }
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setState("idle"), 2000);
  }

  return (
    <button
      className={`${className} copy-feedback ${state === "copied" ? "is-copied" : ""}`}
      type="button"
      onClick={handleClick}
    >
      <span aria-live="polite">
        {state === "copied" ? copiedLabel : state === "failed" ? "複製失敗，請手動選取" : label}
      </span>
    </button>
  );
}

function EvidencePanel({ finding }) {
  const evidenceJson = formatEvidenceJson(finding.evidence_json);
  const hasEvidence =
    finding.evidence || finding.rule_id || finding.evidence_type || finding.evidence_source || evidenceJson;

  if (!hasEvidence) {
    return (
      <div className="evidence-panel is-empty">
        <p className="evidence-panel-title">Deterministic Evidence</p>
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

      <CopyButton
        className="secondary-button evidence-copy-button"
        text={buildEvidenceCopyText(finding)}
        label="複製 Evidence"
      />
    </details>
  );
}

/**
 * 選取中的 finding：問題、修補方向、可追溯證據與交給 AI 的 prompt。
 * 關閉會移除網址上的 ?finding=，不影響頁面頁籤。
 */
function FindingDetail({ finding, pageLabel, onClose }) {
  return (
    <article className={`finding-detail sev-${finding.severity}`} aria-labelledby="finding-detail-title">
      <header className="finding-detail-head">
        <div className="finding-detail-tags">
          <span className={`severity ${finding.severity}`}>{SEVERITY_LABEL[finding.severity] || finding.severity}</span>
          <span className={`category-pill cat-${finding.category}`}>
            {(CATEGORY_LABELS[finding.category] || finding.category || "").toUpperCase()}
          </span>
        </div>
        <button type="button" className="finding-detail-close" onClick={onClose} aria-label="關閉問題詳情">
          ×
        </button>
      </header>
      <h3 className="finding-detail-title" id="finding-detail-title">
        {finding.title}
      </h3>
      {pageLabel && <p className="finding-detail-page">{pageLabel}</p>}
      {finding.description && <p className="finding-detail-text">{finding.description}</p>}
      {finding.remediation && (
        <div className="finding-detail-fix">
          <p className="finding-detail-fix-label">修補方向</p>
          <p>{finding.remediation}</p>
        </div>
      )}
      <EvidencePanel finding={finding} />
      <CopyButton className="primary-button finding-detail-prompt" text={finding.ai_handoff_prompt} label="複製問題 Prompt" />
    </article>
  );
}

export default FindingDetail;
