import { IrisScore, scoreTone } from "../brand/IrisScore";
import { ScanStatusBadge } from "./ScanBadges.jsx";
import { CATEGORY_LABELS } from "../../shared/AppShared.jsx";
import { formatDateTime, formatNumber } from "../../shared/formatters";

const DIMENSION_ORDER = ["seo", "aeo", "geo", "security", "ux"];

/** 各維度分數：品牌維度色的細條＋數字；只列後端真的有分數的維度。 */
function DimensionScores({ scores }) {
  const entries = DIMENSION_ORDER.filter((key) => typeof scores?.[key] === "number");
  if (!entries.length) return null;
  return (
    <ul className="report-dims" aria-label="各維度分數">
      {entries.map((key) => {
        const value = Math.round(scores[key]);
        return (
          <li key={key} className={`report-dim cat-${key}`}>
            <span className="report-dim-label">{CATEGORY_LABELS[key]}</span>
            <span className="report-dim-track" aria-hidden="true">
              <span className="report-dim-fill" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
            </span>
            <span className={`report-dim-value ag-num tone-${scoreTone(value)}`}>{value}</span>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * 互動報告的標頭：像健檢報告的封面——目標網址、狀態、規模、總分與各維度分數，
 * 以及唯一的主要動作「匯出 Word」。
 */
function ReportHeader({ scan, onDownload, downloading = false }) {
  const completed = scan.status === "completed";
  const hasScore = scan.overall_score !== null && scan.overall_score !== undefined;
  return (
    <header className="panel report-head">
      <div className="report-head-main">
        <p className="ag-eyebrow">Argus 健檢報告 · #{scan.id}</p>
        <h1 className="report-head-url" title={scan.origin}>
          {scan.origin}
        </h1>
        <div className="report-head-meta">
          <ScanStatusBadge status={scan.status} />
          {scan.scan_mode && (
            <span className={`report-mode-chip is-${scan.scan_mode}`}>
              {scan.scan_mode === "active" ? "主動測試" : "被動偵測"}
            </span>
          )}
          <span className="report-head-stat">
            <strong className="ag-num">{formatNumber(scan.pages_count ?? 0)}</strong> 頁
          </span>
          <span className="report-head-stat">
            <strong className="ag-num">{formatNumber(scan.findings_count ?? 0)}</strong> 項發現
          </span>
          {scan.completed_at && completed && (
            <span className="report-head-stat is-time">完成於 {formatDateTime(scan.completed_at)}</span>
          )}
        </div>
        <div className="report-head-actions">
          <button
            className="primary-button report-export"
            type="button"
            onClick={onDownload}
            disabled={!completed || downloading}
          >
            {downloading ? "匯出中…" : "匯出 Word 報告"}
          </button>
          {!completed && <span className="report-head-note">掃描完成後可匯出</span>}
        </div>
      </div>
      {/* 還沒有分數（進行中、失敗）時不畫空的分數環，把版面留給進度 */}
      {(hasScore || Object.keys(scan.category_scores || {}).length > 0) && (
        <div className="report-head-score">
          <IrisScore score={hasScore ? scan.overall_score : null} size={128} caption="總分" />
          <DimensionScores scores={scan.category_scores} />
        </div>
      )}
    </header>
  );
}

export default ReportHeader;
