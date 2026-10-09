/**
 * 互動報告預覽（示意）：左邊是問題清單，右邊是頁面截圖示意；點一個問題，
 * 截圖上對應的元素會被框起來並顯示證據。沒有操作時每 3.2 秒自動換下一個，
 * 使用者點過之後就停止自動切換。偏好減少動態時不自動切換。
 */
import { useEffect, useRef, useState } from "react";

import { useInView, usePrefersReducedMotion } from "./HomeMotion.jsx";

// box：在頁面示意圖上的位置（百分比）
const FINDINGS = [
  {
    sev: "medium", sevLabel: "中", title: "按鈕沒有可辨識的名稱", dim: "UX",
    evidence: '<button class="slider-next"><img src="arrow.svg"></button>',
    box: { left: 82, top: 30, width: 12, height: 14 },
  },
  {
    sev: "low", sevLabel: "低", title: "圖片缺少替代文字", dim: "SEO",
    evidence: '<img src="hero.jpg">',
    box: { left: 6, top: 22, width: 74, height: 32 },
  },
  {
    sev: "medium", sevLabel: "中", title: "表單欄位沒有標籤", dim: "UX",
    evidence: '<input type="email" placeholder="Email">',
    box: { left: 6, top: 66, width: 52, height: 10 },
  },
];

export default function ReportPreview() {
  const [active, setActive] = useState(0);
  const [manual, setManual] = useState(false);
  const ref = useRef(null);
  const visible = useInView(ref);
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    if (manual || reduced || !visible) return undefined;
    const timer = setInterval(() => setActive((i) => (i + 1) % FINDINGS.length), 3200);
    return () => clearInterval(timer);
  }, [manual, reduced, visible]);

  const current = FINDINGS[active];
  return (
    <div ref={ref} className="hx-preview hx-report">
      <div className="hx-preview-bar">
        <span>互動報告</span>
        <span className="hx-live-tag">示意</span>
      </div>
      <div className="hx-report-grid">
        <ul className="hx-report-list" aria-label="問題清單">
          {FINDINGS.map((finding, index) => (
            <li key={finding.title}>
              <button
                type="button"
                className={`hx-report-item${index === active ? " is-active" : ""}`}
                aria-pressed={index === active}
                onClick={() => { setActive(index); setManual(true); }}
              >
                <span className={`hx-status is-${finding.sev}`}>{finding.sevLabel}</span>
                <span className="hx-report-item-text">
                  <span>{finding.title}</span>
                  <small>{finding.dim}</small>
                </span>
              </button>
            </li>
          ))}
        </ul>
        <div className="hx-report-shot" aria-hidden="true">
          <span className="hx-mock-nav" />
          <span className="hx-mock-hero" />
          <span className="hx-mock-arrow" />
          <span className="hx-mock-line" />
          <span className="hx-mock-line is-short" />
          <span className="hx-mock-input" />
          <span
            className="hx-report-box"
            style={{
              left: `${current.box.left}%`,
              top: `${current.box.top}%`,
              width: `${current.box.width}%`,
              height: `${current.box.height}%`,
            }}
          />
        </div>
      </div>
      <p className="hx-report-evidence" aria-live="polite">
        <span className="hx-report-evidence-label">證據</span>
        <code>{current.evidence}</code>
      </p>
    </div>
  );
}
