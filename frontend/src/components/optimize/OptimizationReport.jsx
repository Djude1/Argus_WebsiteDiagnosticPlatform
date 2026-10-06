import { useMemo, useState } from "react";

import ComparisonViewer from "./ComparisonViewer";
import {
  CATEGORY_LABELS,
  CHANGE_GROUPS,
  OWNER_LABELS,
  SEVERITY_LABELS,
  changeGroup,
  metricValue,
} from "./optimizeLabels";

const FINDINGS_PREVIEW = 6;

/** 一頁看懂「原始 → 發現的問題 → 修改 → 優化後 → 改善效果」。 */
function StoryStrip({ findings, applied, visual, technical, improvedMetrics }) {
  const steps = [
    { key: "compare", label: "原始頁面", value: "Before" },
    { key: "findings", label: "發現的問題", value: `${findings} 項` },
    { key: "changes", label: "Argus 的修改", value: `${applied} 項`, sub: `視覺 ${visual}・技術 ${technical}` },
    { key: "compare", label: "優化後頁面", value: "After" },
    { key: "metrics", label: "可量測的改善", value: `${improvedMetrics} 項` },
  ];
  return (
    <ol className="opt-story" aria-label="優化流程">
      {steps.map((step, index) => (
        <li key={`${step.key}-${index}`}>
          <a href={`#opt-${step.key}`} className="opt-story-step">
            <span className="opt-story-label">{step.label}</span>
            <span className="opt-story-value">{step.value}</span>
            {step.sub && <span className="opt-story-sub">{step.sub}</span>}
          </a>
        </li>
      ))}
    </ol>
  );
}

function ChangeItem({ edit }) {
  const ok = edit.applied > 0;
  return (
    <li className={`opt-change ${ok ? "" : "is-skipped"}`}>
      <div className="opt-change-head">
        <span className={`opt-chip is-${edit.layer === "visual" ? "visual" : "technical"}`}>
          {CATEGORY_LABELS[edit.category] || (edit.layer === "visual" ? "視覺" : "技術")}
        </span>
        <p className="opt-change-impact">{edit.impact || edit.why || "（未說明）"}</p>
        <span className="opt-change-status">
          {ok
            ? edit.applied > 1 ? `已套用 ${edit.applied} 處` : "已套用"
            : edit.rejected ? "已拒絕" : "未套用"}
        </span>
      </div>
      {edit.impact && edit.why && <p className="opt-change-why">原因：{edit.why}</p>}
      {!ok && (
        <p className="opt-change-why">
          {edit.rejected || "修改的位置與原始頁面對不上，這一項沒有套用。"}
        </p>
      )}
    </li>
  );
}

function ChangeList({ edits }) {
  const [group, setGroup] = useState("all");
  const counts = useMemo(() => {
    const out = {};
    edits.forEach((edit) => {
      const key = changeGroup(edit);
      out[key] = (out[key] || 0) + 1;
    });
    return out;
  }, [edits]);
  const visible = group === "all" ? edits : edits.filter((edit) => changeGroup(edit) === group);
  // 視覺改善排最前面：使用者最在意「看得出什麼不同」
  const ordered = [...visible].sort(
    (a, b) => (a.layer === "visual" ? 0 : 1) - (b.layer === "visual" ? 0 : 1),
  );

  return (
    <section className="opt-section" id="opt-changes" aria-labelledby="opt-changes-title">
      <div className="opt-section-head">
        <h2 id="opt-changes-title" className="opt-section-title">Argus 做了哪些修改</h2>
        <div className="opt-segment is-wrap" role="tablist" aria-label="修改分類">
          <button
            type="button"
            role="tab"
            aria-selected={group === "all"}
            className={group === "all" ? "is-active" : ""}
            onClick={() => setGroup("all")}
          >
            全部 {edits.length}
          </button>
          {CHANGE_GROUPS.filter((item) => counts[item.key]).map((item) => (
            <button
              key={item.key}
              type="button"
              role="tab"
              aria-selected={group === item.key}
              className={group === item.key ? "is-active" : ""}
              onClick={() => setGroup(item.key)}
            >
              {item.label} {counts[item.key]}
            </button>
          ))}
        </div>
      </div>
      {ordered.length === 0 ? (
        <p className="opt-muted">這次沒有提出修改。</p>
      ) : (
        <ul className="opt-changes">
          {ordered.map((edit, index) => (
            <ChangeItem key={index} edit={edit} />
          ))}
        </ul>
      )}
    </section>
  );
}

function Findings({ findings }) {
  const [expanded, setExpanded] = useState(false);
  const counts = findings.reduce((acc, f) => ({ ...acc, [f.severity]: (acc[f.severity] || 0) + 1 }), {});
  const shown = expanded ? findings : findings.slice(0, FINDINGS_PREVIEW);
  return (
    <section className="opt-section" id="opt-findings" aria-labelledby="opt-findings-title">
      <div className="opt-section-head">
        <h2 id="opt-findings-title" className="opt-section-title">掃描發現的問題</h2>
        <p className="opt-severity-counts">
          {Object.keys(SEVERITY_LABELS)
            .filter((key) => counts[key])
            .map((key) => (
              <span key={key} className={`opt-sev is-${key}`}>
                {SEVERITY_LABELS[key]} {counts[key]}
              </span>
            ))}
        </p>
      </div>
      {findings.length === 0 ? (
        <p className="opt-muted">這一頁沒有掃描發現的問題；Argus 只做了視覺與使用體驗的改善。</p>
      ) : (
        <>
          <ul className="opt-findings">
            {shown.map((finding, index) => (
              <li key={index}>
                <span className={`opt-sev is-${finding.severity}`}>{SEVERITY_LABELS[finding.severity] || finding.severity}</span>
                {finding.title}
              </li>
            ))}
          </ul>
          {findings.length > FINDINGS_PREVIEW && (
            <button type="button" className="opt-text-button" onClick={() => setExpanded(!expanded)}>
              {expanded ? "收合" : `顯示全部 ${findings.length} 項`}
            </button>
          )}
        </>
      )}
    </section>
  );
}

function Metrics({ metrics }) {
  return (
    <section className="opt-section" id="opt-metrics" aria-labelledby="opt-metrics-title">
      <h2 id="opt-metrics-title" className="opt-section-title">可量測的改善</h2>
      {metrics.length === 0 ? (
        <p className="opt-muted">這次的修改沒有改變可自動量測的指標，差異主要在畫面上，請看上方的前後比較。</p>
      ) : (
        <table className="opt-metrics">
          <thead>
            <tr>
              <th scope="col">項目</th>
              <th scope="col">優化前</th>
              <th scope="col">優化後</th>
            </tr>
          </thead>
          <tbody>
            {metrics.map((row) => (
              <tr key={row.key}>
                <th scope="row">{row.label}</th>
                <td>{metricValue(row.before)}</td>
                <td className={row.improved === true ? "is-better" : row.improved === false ? "is-worse" : ""}>
                  {metricValue(row.after)}
                  {row.improved === true && <span className="opt-better">改善</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function NotHandled({ items }) {
  if (!items.length) return null;
  return (
    <section className="opt-section" aria-labelledby="opt-todo-title">
      <h2 id="opt-todo-title" className="opt-section-title">需要其他人處理的項目</h2>
      <p className="opt-muted">這些問題無法在頁面 HTML 裡修好，需要轉給對應的負責人。</p>
      <ul className="opt-todo">
        {items.map((item, index) => (
          <li key={index}>
            {item.owner && <span className="opt-owner">{OWNER_LABELS[item.owner]}</span>}
            <span className="opt-todo-item">{item.item}</span>
            {item.reason && <span className="opt-todo-reason">{item.reason}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * 優化結果（擁有者頁與公開分享頁共用，唯讀）。
 * data：{ edits, outcome: {summary, not_handled, metrics}, findings, has_original, has_optimized }
 */
export default function OptimizationReport({ data, loadHtml }) {
  const edits = data.edits || [];
  const outcome = data.outcome || {};
  const metrics = outcome.metrics || [];
  const applied = edits.filter((edit) => edit.applied > 0);
  const visual = applied.filter((edit) => edit.layer === "visual").length;

  return (
    <div className="opt-report">
      {outcome.summary && <p className="opt-summary">{outcome.summary}</p>}
      <StoryStrip
        findings={(data.findings || []).length}
        applied={applied.length}
        visual={visual}
        technical={applied.length - visual}
        improvedMetrics={metrics.filter((row) => row.improved === true).length}
      />
      <div id="opt-compare">
        <ComparisonViewer
          loadHtml={loadHtml}
          hasOriginal={data.has_original}
          hasOptimized={data.has_optimized}
        />
      </div>
      <div className="opt-columns">
        <ChangeList edits={edits} />
        <div className="opt-side">
          <Metrics metrics={metrics} />
          <Findings findings={data.findings || []} />
        </div>
      </div>
      <NotHandled items={outcome.not_handled || []} />
    </div>
  );
}
