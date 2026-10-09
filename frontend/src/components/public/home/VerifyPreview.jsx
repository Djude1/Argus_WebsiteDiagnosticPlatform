/**
 * 報告查驗預覽（示意）：進入畫面後依序播放「輸入報告編號 → 比對內容指紋 → 內容一致」，
 * 播完停在結果；按「重新查驗」可再播一次。偏好減少動態時直接顯示結果。
 * 報告編號以「•」遮住，不示範任何真實或虛構的編號格式。
 */
import { useEffect, useRef, useState } from "react";

import { useInViewOnce, usePrefersReducedMotion } from "./HomeMotion.jsx";

const STEPS = ["idle", "typing", "checking", "ok"];
const DELAYS = { idle: 500, typing: 1100, checking: 1300 };

export default function VerifyPreview() {
  const ref = useRef(null);
  const seen = useInViewOnce(ref);
  const reduced = usePrefersReducedMotion();
  const [step, setStep] = useState("idle");
  const [round, setRound] = useState(0);

  useEffect(() => {
    if (!seen) return undefined;
    if (reduced) {
      setStep("ok");
      return undefined;
    }
    if (step === "ok") return undefined;
    const timer = setTimeout(() => setStep(STEPS[STEPS.indexOf(step) + 1]), DELAYS[step]);
    return () => clearTimeout(timer);
  }, [seen, reduced, step, round]);

  const restart = () => {
    setStep(reduced ? "ok" : "idle");
    setRound((r) => r + 1);
  };

  const typed = step === "idle" ? "" : "••••-••••-••••";
  return (
    <div ref={ref} className="hx-preview hx-verify">
      <div className="hx-preview-bar">
        <span>報告查驗</span>
        <span className="hx-live-tag">示意</span>
      </div>
      <div className="hx-verify-body">
        <div className="hx-verify-doc" aria-hidden="true">
          <span className="hx-verify-doc-head" />
          <span className="hx-mock-line" />
          <span className="hx-mock-line" />
          <span className="hx-mock-line is-short" />
          <span className="hx-verify-stamp">PDF</span>
        </div>
        <div className="hx-verify-form">
          <span className="hx-verify-label">報告編號</span>
          <span className={`hx-verify-input${step === "typing" ? " is-typing" : ""}`}>
            {typed || <span className="hx-verify-placeholder">輸入報告上的編號</span>}
          </span>
          <div className="hx-verify-result" aria-live="polite">
            {step === "checking" && <span className="hx-status is-running">比對內容指紋中</span>}
            {step === "ok" && <span className="hx-status is-pass">內容與原始報告一致</span>}
          </div>
          <button type="button" className="hx-verify-again" onClick={restart} disabled={step !== "ok"}>
            重新查驗
          </button>
        </div>
      </div>
    </div>
  );
}
