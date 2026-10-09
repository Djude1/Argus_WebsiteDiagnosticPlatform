/**
 * 「檢測面向」分頁：左側五個面向（tablist，方向鍵切換），右側顯示該面向檢查什麼。
 * 切換時內容淡入並由右滑入；每一項檢查都對應 backend/apps/scans 的實際規則。
 */
import { useRef, useState } from "react";

import { GlowCard } from "./HomeMotion.jsx";

export default function CoverageTabs({ items }) {
  const [active, setActive] = useState(0);
  const tabRefs = useRef([]);
  const item = items[active];
  const Icon = item.Icon;

  const onKeyDown = (event) => {
    const keys = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 };
    if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      const next = event.key === "Home" ? 0 : items.length - 1;
      setActive(next);
      tabRefs.current[next]?.focus();
      return;
    }
    if (!(event.key in keys)) return;
    event.preventDefault();
    const next = (active + keys[event.key] + items.length) % items.length;
    setActive(next);
    tabRefs.current[next]?.focus();
  };

  return (
    <div className="hx-cov">
      <div className="hx-cov-tabs" role="tablist" aria-label="檢測面向" aria-orientation="vertical">
        {items.map((tab, index) => {
          const TabIcon = tab.Icon;
          const selected = index === active;
          return (
            <button
              key={tab.key}
              ref={(node) => { tabRefs.current[index] = node; }}
              type="button"
              role="tab"
              id={`hx-cov-tab-${tab.key}`}
              aria-selected={selected}
              aria-controls="hx-cov-panel"
              tabIndex={selected ? 0 : -1}
              className={`hx-cov-tab${selected ? " is-active" : ""}`}
              data-cat={tab.key}
              onClick={() => setActive(index)}
              onKeyDown={onKeyDown}
            >
              <span className="hx-cov-tab-icon"><TabIcon /></span>
              <span className="hx-cov-tab-text">
                <strong>{tab.code}</strong>
                <span>{tab.name}</span>
              </span>
            </button>
          );
        })}
      </div>
      <GlowCard
        className="hx-cov-panel"
        id="hx-cov-panel"
        role="tabpanel"
        aria-labelledby={`hx-cov-tab-${item.key}`}
      >
        <div className="hx-cov-panel-inner" key={item.key} data-cat={item.key}>
          <div className="hx-cov-panel-head">
            <span className="hx-cov-panel-icon"><Icon /></span>
            <div>
              <p className="hx-cov-panel-code">{item.code}</p>
              <h3 className="hx-cov-panel-title">{item.name}</h3>
            </div>
          </div>
          <p className="hx-cov-panel-desc">{item.desc}</p>
          <ul className="hx-dashes">
            {item.checks.map((check, i) => (
              <li key={check} style={{ "--i": i }}>
                <span className="hx-dash" aria-hidden="true" />
                {check}
              </li>
            ))}
          </ul>
        </div>
      </GlowCard>
    </div>
  );
}
