import { useEffect, useState } from "react";

import { ArgusMark } from "../brand/ArgusMark";
import { StatusDoneGlyph } from "../../shared/AppShared.jsx";

// 階段 stepper：只列後端真的會回報的狀態（ScanJob.Status）。
// 「評分」在掃描完成那一刻才發生，進行中永遠不會是 active，只作為終點提示。
function buildSteps(scanMode) {
  return [
    { key: "queued", label: "授權確認", sub: "排隊中" },
    { key: "crawling", label: "爬取", sub: "BFS 爬頁與截圖" },
    {
      key: "scanning",
      label: scanMode === "active" ? "規則＋主動工具" : "規則引擎",
      sub: scanMode === "active" ? "被動規則與主動測試" : "SEO／AEO／GEO／資安／UX",
    },
    { key: "agent_testing", label: "Agent 測試", sub: "AI 解釋高優先問題" },
    { key: "completed", label: "評分", sub: "產出報告" },
  ];
}

const PHASE_TITLE = {
  queued: "排隊等待中",
  crawling: "正在爬取網站頁面",
  scanning: "規則引擎分析中",
  agent_testing: "AI Agent 測試中",
};

const RING_TICKS = 24;
const RING_TICK_LIST = Array.from({ length: RING_TICKS }, (_, i) => {
  const angle = (i / RING_TICKS) * Math.PI * 2 - Math.PI / 2;
  return {
    x1: 60 + Math.cos(angle) * 49,
    y1: 60 + Math.sin(angle) * 49,
    x2: 60 + Math.cos(angle) * 57,
    y2: 60 + Math.sin(angle) * 57,
  };
});

function formatMMSS(totalSec) {
  const sec = Math.max(0, Math.floor(totalSec));
  const mm = String(Math.floor(sec / 60)).padStart(2, "0");
  const ss = String(sec % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

/** 虹膜刻度進度：24 道刻度依百分比點亮；沒有頁數資料時改為旋轉的掃描光。 */
function IrisProgress({ pct }) {
  const determinate = pct !== null;
  const lit = determinate ? Math.round((pct / 100) * RING_TICKS) : 0;
  return (
    <div className={`iris-progress ${determinate ? "" : "is-indeterminate"}`} aria-hidden="true">
      <svg viewBox="0 0 120 120" className="iris-progress-ring">
        <g className="iris-progress-ticks">
          {RING_TICK_LIST.map((tick, index) => {
            let cls = "";
            if (determinate && index < lit) cls = "is-lit";
            if (!determinate && index < 6) cls = `is-trail trail-${index}`;
            return <line key={index} {...tick} className={cls} />;
          })}
        </g>
      </svg>
      <ArgusMark size={52} scanning className="iris-progress-mark" />
      {determinate && <span className="iris-progress-pct ag-num">{pct}%</span>}
    </div>
  );
}

/**
 * 掃描進行中的品牌化進度體驗：虹膜刻度進度、已執行／剩餘時間、階段 stepper。
 * 只顯示後端 ScanJob 真的有的欄位（status、progress、started_at、scan_mode）。
 */
function ScanProgress({ status, scanMode, hint, progress, startedAt, onCancel, cancelBusy = false }) {
  // 每秒重繪，讓「已執行 / 剩餘」會走動
  const [, force] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => force((x) => x + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const steps = buildSteps(scanMode);
  const currentIdx = Math.max(0, steps.findIndex((step) => step.key === status));

  // progress 結構：{pages_done, pages_total, phase, phase_started_at}
  const total = progress?.pages_total || 0;
  const done = progress?.pages_done || 0;
  const hasProgress = total > 0;
  const pct = hasProgress ? Math.min(100, Math.round((done / total) * 100)) : null;

  // 已執行時間（從整個 scan 的 started_at 起算）
  const scanStart = startedAt ? new Date(startedAt).getTime() : null;
  const elapsedSec = scanStart ? Math.floor((Date.now() - scanStart) / 1000) : null;

  // ETA：基於當前 phase 的 elapsed × (total / done - 1)
  let etaSec = null;
  let etaPending = false;
  if (hasProgress && done > 0 && done < total && progress?.phase_started_at) {
    const phaseStart = new Date(progress.phase_started_at).getTime();
    const phaseElapsed = Math.max(1, Math.floor((Date.now() - phaseStart) / 1000));
    etaSec = Math.max(0, Math.round(phaseElapsed * (total / done - 1)));
  } else if (hasProgress && done === 0) {
    etaPending = true;
  }

  const title =
    status === "scanning" && scanMode === "active"
      ? "規則引擎與主動工具檢測中"
      : PHASE_TITLE[status] || "處理中";

  return (
    <section className="scan-progress ag-surface-grid" aria-label="掃描進度">
      <div className="scan-progress-top">
        <IrisProgress pct={pct} />
        <div className="scan-progress-text">
          <p className="ag-eyebrow">
            掃描進行中 · 第 {currentIdx + 1}/{steps.length} 階段
          </p>
          <h3 className="scan-progress-title" aria-live="polite">
            {title}
          </h3>
          {hint ? <p className="scan-progress-hint">{hint}</p> : null}
          {(elapsedSec !== null || hasProgress) && (
            <dl className="scan-progress-meta">
              {elapsedSec !== null && (
                <div>
                  <dt>已執行</dt>
                  <dd className="ag-num">{formatMMSS(elapsedSec)}</dd>
                </div>
              )}
              {hasProgress && (
                <div>
                  <dt>本階段</dt>
                  <dd className="ag-num">
                    {done}/{total} 頁
                  </dd>
                </div>
              )}
              {etaSec !== null ? (
                <div className="is-eta">
                  <dt>剩餘約</dt>
                  <dd className="ag-num">{formatMMSS(etaSec)}</dd>
                </div>
              ) : etaPending ? (
                <div className="is-eta">
                  <dt>剩餘時間</dt>
                  <dd>估算中…</dd>
                </div>
              ) : null}
            </dl>
          )}
        </div>
        {onCancel ? (
          <button type="button" className="scan-cancel-button" onClick={onCancel} disabled={cancelBusy}>
            {cancelBusy ? "終止中…" : "終止掃描"}
          </button>
        ) : null}
      </div>

      <div
        className={`scan-progress-bar ${hasProgress ? "is-determinate" : ""}`}
        role="progressbar"
        aria-label="掃描進度"
        aria-valuenow={pct ?? undefined}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        {hasProgress ? (
          <div className="scan-progress-fill" style={{ width: `${pct}%` }} />
        ) : (
          <div className="scan-progress-sweep" />
        )}
      </div>

      <ol className="scan-stepper">
        {steps.map((step, idx) => {
          let state = "pending";
          if (idx < currentIdx) state = "done";
          else if (idx === currentIdx) state = "active";
          return (
            <li
              key={step.key}
              className={`scan-stepper-item is-${state}`}
              aria-current={state === "active" ? "step" : undefined}
            >
              <span className="scan-stepper-dot" aria-hidden="true">
                {state === "done" ? <StatusDoneGlyph /> : idx + 1}
              </span>
              <span className="scan-stepper-label">{step.label}</span>
              <span className="scan-stepper-sub">{step.sub}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

export default ScanProgress;
