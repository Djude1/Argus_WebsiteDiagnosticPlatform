/**
 * 「運作方式」堆疊卡片輪播：最前面一張完整顯示，後面的卡片往上錯開 16px、逐張縮小 10%，
 * 每 2.5 秒把最前面那張移到最後。滑鼠移入、鍵盤聚焦、不在畫面內、偏好減少動態時暫停；
 * 下方的步驟按鈕可以直接切到某一步（也讓看不到動畫的人能逐步閱讀）。
 */
import { useEffect, useRef, useState } from "react";

import { GlowCard, useInView, usePrefersReducedMotion } from "./HomeMotion.jsx";

const INTERVAL_MS = 2500;

export default function ProcessStack({ steps }) {
  const [order, setOrder] = useState(() => steps.map((_, i) => i));
  const [paused, setPaused] = useState(false);
  const ref = useRef(null);
  const visible = useInView(ref);
  const reduced = usePrefersReducedMotion();
  const running = visible && !paused && !reduced;

  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(() => {
      setOrder((prev) => [...prev.slice(1), prev[0]]);
    }, INTERVAL_MS);
    return () => clearInterval(timer);
  }, [running]);

  const bringToFront = (index) => {
    setOrder((prev) => {
      const at = prev.indexOf(index);
      return [...prev.slice(at), ...prev.slice(0, at)];
    });
  };

  return (
    <div
      ref={ref}
      className="hx-stack"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
    >
      <div className="hx-stack-cards">
        {steps.map((step, index) => {
          const depth = order.indexOf(index);
          const Icon = step.Icon;
          return (
            <div
              key={step.title}
              className="hx-stack-item"
              aria-hidden={depth !== 0}
              style={{
                "--depth": depth,
                zIndex: steps.length - depth,
              }}
            >
              <GlowCard className="hx-stack-card">
                <span className="hx-stack-icon"><Icon /></span>
                <p className="hx-stack-step">步驟 {String(index + 1).padStart(2, "0")}</p>
                <h3 className="hx-stack-title">{step.title}</h3>
                <p className="hx-stack-desc">{step.desc}</p>
              </GlowCard>
            </div>
          );
        })}
      </div>
      <div className="hx-stack-dots" role="group" aria-label="切換步驟">
        {steps.map((step, index) => (
          <button
            key={step.title}
            type="button"
            className={`hx-stack-dot${order[0] === index ? " is-active" : ""}`}
            aria-pressed={order[0] === index}
            aria-label={`步驟 ${index + 1}：${step.title}`}
            onClick={() => bringToFront(index)}
          >
            <span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
            <span className="hx-stack-dot-label">{step.short}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
