import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { IrisScore, scoreTone } from "../brand/IrisScore";
import { ScanStatusBadge } from "./ScanBadges.jsx";
import { isInProgress } from "../../shared/AppShared.jsx";
import { formatRelative } from "../../shared/formatters";

export const LIST_POLL_INTERVAL_MS = 3000;

function hostOf(origin) {
  return (origin || "").replace(/^https?:\/\//, "");
}

/** 列表載入中的骨架：三張卡的輪廓，避免空白閃一下才出現內容。 */
function ScanListSkeleton() {
  return (
    <div className="scan-list-items" aria-hidden="true">
      {[0, 1, 2].map((key) => (
        <div className="scan-card is-skeleton" key={key}>
          <span className="scan-skel scan-skel-ring" />
          <span className="scan-card-body">
            <span className="scan-skel scan-skel-line" />
            <span className="scan-skel scan-skel-line is-short" />
          </span>
        </div>
      ))}
    </div>
  );
}

/**
 * 掃描列表：同網址只顯示最新一次。每張卡片＝分數環、網址（mono）、狀態、時間，
 * 與同網址上一次分數的差值。
 */
function ScanList({ scans, loading = false, onRefresh }) {
  const navigate = useNavigate();
  const { scanId } = useParams();
  const activeId = scanId ? Number(scanId) : null;
  const inProgressCount = scans.filter((scan) => isInProgress(scan.status)).length;

  // 每個 origin 上一次的分數，用來算 delta（同 origin 的 scans 已按 -created_at 排序）
  const previousByOrigin = useMemo(() => {
    const seen = new Map();
    const result = new Map();
    for (const scan of scans) {
      if (scan.overall_score === null || scan.overall_score === undefined) continue;
      if (seen.has(scan.origin)) {
        // 第二次見到此 origin，視為「上一次分數」對應第一次見到的那筆
        const firstScanId = seen.get(scan.origin);
        if (!result.has(firstScanId)) {
          result.set(firstScanId, scan.overall_score);
        }
      } else {
        seen.set(scan.origin, scan.id);
      }
    }
    return result;
  }, [scans]);

  return (
    <section className="panel scan-list" aria-labelledby="scan-list-title">
      <header className="scan-list-head">
        <div>
          <p className="ag-eyebrow">任務</p>
          <h2 className="section-title" id="scan-list-title">
            掃描列表
            {scans.length > 0 && <span className="scan-list-count ag-num">{scans.length}</span>}
          </h2>
        </div>
        <button className="secondary-button scan-list-refresh" type="button" onClick={onRefresh}>
          重新整理
        </button>
      </header>
      {inProgressCount > 0 && (
        <p className="scan-list-live" role="status">
          <span className="scan-live-dot" aria-hidden="true" />
          {inProgressCount} 個進行中，每 {LIST_POLL_INTERVAL_MS / 1000} 秒自動更新
        </p>
      )}
      <p className="scan-list-note">
        同網址僅顯示最新一次掃描。
        <button type="button" className="scan-list-history" onClick={() => navigate("/history")}>
          查看歷史 →
        </button>
      </p>

      {loading && !scans.length ? (
        <ScanListSkeleton />
      ) : (
        <ul className="scan-list-items">
          {scans.map((scan) => {
            const score = scan.overall_score;
            const tone = scoreTone(score);
            const previous = previousByOrigin.get(scan.id);
            const delta =
              previous !== undefined && score !== null && score !== undefined ? score - previous : null;
            const live = isInProgress(scan.status);
            return (
              <li key={scan.id}>
                <button
                  className={`scan-card tone-${tone === "none" ? "muted" : tone} ${
                    activeId === scan.id ? "active" : ""
                  } ${live ? "is-in-progress" : ""}`}
                  type="button"
                  onClick={() => navigate(`/scans/${scan.id}`)}
                  aria-current={activeId === scan.id ? "page" : undefined}
                >
                  <IrisScore score={score} size={44} className="scan-card-score" />
                  <span className="scan-card-body">
                    <span className="scan-card-origin" title={scan.origin}>
                      {hostOf(scan.origin)}
                    </span>
                    <span className="scan-card-meta">
                      <ScanStatusBadge status={scan.status} />
                      {delta !== null && delta !== 0 && (
                        <span
                          className={`scan-card-delta tone-${delta > 0 ? "good" : "bad"}`}
                          title="與該網址上一次分數比較"
                        >
                          {delta > 0 ? `▲ +${delta}` : `▼ ${delta}`}
                        </span>
                      )}
                      {scan.created_at && (
                        <span className="scan-card-time">{formatRelative(scan.created_at)}</span>
                      )}
                    </span>
                  </span>
                  {live && <span className="scan-card-progress-shimmer" aria-hidden="true" />}
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {!loading && !scans.length && (
        <div className="scan-list-empty">
          <p className="scan-list-empty-title">還沒有掃描任務</p>
          <p className="hint-text">填好「建立授權掃描」表單並確認授權，就能建立第一個健檢報告。</p>
        </div>
      )}
    </section>
  );
}

export default ScanList;
