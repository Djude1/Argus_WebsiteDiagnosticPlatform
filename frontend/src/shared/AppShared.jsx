import { useEffect, useRef, useState } from "react";

const CATEGORY_FILTERS = [
  { value: "all", label: "全部分類" },
  { value: "seo", label: "SEO" },
  { value: "aeo", label: "AEO" },
  { value: "geo", label: "GEO" },
  { value: "security", label: "資安" },
  { value: "ux", label: "UX" },
];

const SEVERITY_FILTERS = [
  { value: "all", label: "全部嚴重度" },
  { value: "critical", label: "嚴重" },
  { value: "high", label: "高" },
  { value: "medium", label: "中" },
  { value: "low", label: "低" },
  { value: "info", label: "資訊" },
];

const STATUS_LABELS = {
  queued: { label: "等待中", tone: "slate", emoji: "⏳" },
  crawling: { label: "爬取中", tone: "blue", emoji: "🕷️" },
  scanning: { label: "掃描中", tone: "blue", emoji: "🔍" },
  agent_testing: { label: "Agent 測試中", tone: "blue", emoji: "🤖" },
  completed: { label: "完成", tone: "emerald", emoji: "✓" },
  failed: { label: "失敗", tone: "red", emoji: "✗" },
  cancelled: { label: "已終止", tone: "slate", emoji: "✖" },
};

const IN_PROGRESS_STATUSES = ["queued", "crawling", "scanning", "agent_testing"];

function isInProgress(status) {
  return IN_PROGRESS_STATUSES.includes(status);
}

// ============================================================
// 視覺化元件（純 SVG / CSS，無 chart 套件）
// ============================================================

const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"];
const SEVERITY_COLOR = {
  critical: "#dc2626",
  high: "#f97316",
  medium: "#facc15",
  low: "#38bdf8",
  info: "#94a3b8",
};
const SEVERITY_LABEL = {
  critical: "嚴重",
  high: "高",
  medium: "中",
  low: "低",
  info: "資訊",
};
const CATEGORY_COLOR = {
  security: "#ef4444",
  seo: "#6366f1",
  aeo: "#a855f7",
  geo: "#06b6d4",
  ux: "#10b981",
};

function apiErrorMessage(err, fallback = "操作失敗，請稍後再試。") {
  const data = err?.response?.data;
  if (!data) return fallback;
  if (typeof data === "string") return data;
  if (data.detail) return data.detail;
  const firstKey = Object.keys(data)[0];
  const firstValue = firstKey ? data[firstKey] : null;
  if (Array.isArray(firstValue)) return firstValue.join(" ");
  if (typeof firstValue === "string") return firstValue;
  return fallback;
}

const DIALOG_FOCUSABLE_SELECTOR = [
  "button:not([disabled])",
  "a[href]",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function useDialogFocus(isOpen, onClose) {
  const dialogRef = useRef(null);
  const closeRef = useRef(onClose);
  const previousFocusRef = useRef(null);
  closeRef.current = onClose;

  useEffect(() => {
    if (!isOpen) return undefined;
    const dialog = dialogRef.current;
    if (!dialog) return undefined;
    previousFocusRef.current = document.activeElement;
    const firstFocusable = dialog.querySelector(DIALOG_FOCUSABLE_SELECTOR);
    (firstFocusable || dialog).focus();

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = [...dialog.querySelectorAll(DIALOG_FOCUSABLE_SELECTOR)];
      if (!focusable.length) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previousFocusRef.current?.focus();
    };
  }, [isOpen]);

  return dialogRef;
}

// 取代 window.confirm() / window.alert()，維持科技風玻璃擬態視覺語言一致。
// confirmDialog(message) 回傳 Promise<boolean>；notifyDialog(message) 為單按鈕提示，無需 await。
// 使用方式：const { confirmDialog, notifyDialog, dialogHost } = useConfirmDialogs(); 並在 JSX 中 render {dialogHost}。
function useConfirmDialogs() {
  const [dialog, setDialog] = useState(null);
  const dialogRef = useDialogFocus(Boolean(dialog), () => closeDialog(false));

  function closeDialog(result) {
    setDialog((current) => {
      if (current?.kind === "confirm") current.resolve(Boolean(result));
      return null;
    });
  }

  function confirmDialog(message, { danger = false } = {}) {
    return new Promise((resolve) => setDialog({ kind: "confirm", message, danger, resolve }));
  }

  function notifyDialog(message) {
    setDialog({ kind: "notice", message });
  }

  const dialogHost = dialog ? (
    <div className="ann-backdrop" onClick={() => closeDialog(false)}>
      <div
        ref={dialogRef}
        className="ann-modal sm"
        role="alertdialog"
        aria-modal="true"
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="ann-modal-body">
          <p>{dialog.message}</p>
        </div>
        <footer className="ann-modal-footer">
          {dialog.kind === "confirm" && (
            <button type="button" className="ann-btn-dismiss" onClick={() => closeDialog(false)}>取消</button>
          )}
          <button
            type="button"
            className={`ann-btn-confirm${dialog.kind === "confirm" && dialog.danger ? " danger" : ""}`}
            onClick={() => closeDialog(true)}
          >
            {dialog.kind === "confirm" ? "確定" : "知道了"}
          </button>
        </footer>
      </div>
    </div>
  ) : null;

  return { confirmDialog, notifyDialog, dialogHost };
}

// 數字遞增動畫（適可而止：300ms 線性 ease-out）
function CountUp({ value, duration = 600, suffix = "" }) {
  const [display, setDisplay] = useState(0);
  useEffect(() => {
    const target = Number(value) || 0;
    if (target === 0) {
      setDisplay(0);
      return undefined;
    }
    const start = performance.now();
    let frameId = 0;
    const tick = (now) => {
      const elapsed = now - start;
      const progress = Math.min(1, elapsed / duration);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(target * eased);
      if (progress < 1) {
        frameId = requestAnimationFrame(tick);
      } else {
        setDisplay(target);
      }
    };
    frameId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameId);
  }, [value, duration]);
  const rounded = Number.isInteger(value) ? Math.round(display) : Math.round(display * 10) / 10;
  return (
    <span>
      {rounded}
      {suffix}
    </span>
  );
}

// 水平堆疊比例條：data = [{label, value, color}]，按比例填色
function StackedBar({ data, height = 14 }) {
  const total = data.reduce((sum, item) => sum + (item.value || 0), 0);
  if (total === 0) {
    return <div className="stacked-bar empty" style={{ height }} />;
  }
  return (
    <div className="stacked-bar-wrap">
      <div className="stacked-bar" style={{ height }}>
        {data.map((item) => {
          const pct = (item.value / total) * 100;
          if (pct === 0) return null;
          return (
            <div
              className="stacked-bar-seg"
              key={item.label}
              style={{ width: `${pct}%`, background: item.color }}
              title={`${item.label}: ${item.value} (${pct.toFixed(1)}%)`}
            />
          );
        })}
      </div>
      <div className="stacked-bar-legend">
        {data.map((item) => {
          if (!item.value) return null;
          const pct = (item.value / total) * 100;
          return (
            <div key={item.label} className="stacked-bar-legend-item">
              <span
                className="stacked-bar-swatch"
                style={{ background: item.color }}
                aria-hidden="true"
              />
              <span className="stacked-bar-legend-label">{item.label}</span>
              <span className="stacked-bar-legend-value">{Math.round(pct)}%</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// 嚴重度長條圖（水平、按 SEVERITY_ORDER）
function SeverityBarChart({ severityTotals, title = "Findings 嚴重度分佈" }) {
  const max = Math.max(
    ...SEVERITY_ORDER.map((s) => severityTotals?.[s] || 0),
    1,
  );
  const totalFindings = SEVERITY_ORDER.reduce(
    (sum, s) => sum + (severityTotals?.[s] || 0),
    0,
  );
  return (
    <div className="bar-chart">
      <div className="bar-chart-header">
        <h4>{title}</h4>
        <span className="bar-chart-total">共 {totalFindings}</span>
      </div>
      <div className="bar-chart-rows">
        {SEVERITY_ORDER.map((sev) => {
          const count = severityTotals?.[sev] || 0;
          const pct = (count / max) * 100;
          return (
            <div key={sev} className="bar-chart-row">
              <span className={`bar-chart-label severity ${sev}`}>
                {SEVERITY_LABEL[sev]}
              </span>
              <div className="bar-chart-track">
                <div
                  className="bar-chart-fill"
                  style={{
                    width: `${pct}%`,
                    background: SEVERITY_COLOR[sev],
                    boxShadow: `0 0 8px ${SEVERITY_COLOR[sev]}66`,
                  }}
                />
              </div>
              <span className="bar-chart-count">{count}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// 折線圖：分數趨勢（含座標軸、點標註）
// data = [{label, value}]（按時間舊→新排序）
function LineChart({ data, width = 320, height = 110, ariaLabel }) {
  if (!data || data.length === 0) {
    return <div className="line-chart-empty">無資料</div>;
  }
  const padding = { top: 12, right: 12, bottom: 22, left: 30 };
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;
  const values = data.map((d) => d.value).filter((v) => typeof v === "number");
  if (values.length === 0) {
    return <div className="line-chart-empty">無有效分數</div>;
  }
  const minV = 0;
  const maxV = 100;
  const stepX = data.length > 1 ? plotW / (data.length - 1) : 0;
  const yFor = (v) => padding.top + plotH - ((v - minV) / (maxV - minV)) * plotH;
  const xFor = (i) => padding.left + i * stepX;

  const linePoints = data
    .map((d, i) => (typeof d.value === "number" ? `${xFor(i)},${yFor(d.value)}` : null))
    .filter(Boolean)
    .join(" ");

  const yTicks = [0, 50, 100];
  return (
    <svg
      className="line-chart"
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={ariaLabel || "分數趨勢"}
    >
      {/* Y 軸格線與刻度 */}
      {yTicks.map((tick) => (
        <g key={tick}>
          <line
            x1={padding.left}
            x2={width - padding.right}
            y1={yFor(tick)}
            y2={yFor(tick)}
            className="line-chart-grid"
          />
          <text
            x={padding.left - 6}
            y={yFor(tick) + 3}
            className="line-chart-axis-label"
            textAnchor="end"
          >
            {tick}
          </text>
        </g>
      ))}
      {/* 折線 */}
      <polyline points={linePoints} className="line-chart-line" fill="none" />
      {/* 資料點 */}
      {data.map((d, i) => {
        if (typeof d.value !== "number") return null;
        return (
          <g key={i}>
            <circle
              cx={xFor(i)}
              cy={yFor(d.value)}
              r="3.5"
              className="line-chart-dot"
            />
            <text
              x={xFor(i)}
              y={yFor(d.value) - 7}
              className="line-chart-value"
              textAnchor="middle"
            >
              {d.value}
            </text>
          </g>
        );
      })}
      {/* X 軸標籤：只顯示首末，避免擠 */}
      {data.length > 0 && (
        <>
          <text
            x={xFor(0)}
            y={height - 6}
            className="line-chart-axis-label"
            textAnchor="start"
          >
            {data[0].label}
          </text>
          {data.length > 1 && (
            <text
              x={xFor(data.length - 1)}
              y={height - 6}
              className="line-chart-axis-label"
              textAnchor="end"
            >
              {data[data.length - 1].label}
            </text>
          )}
        </>
      )}
    </svg>
  );
}

// 進行中時的 polling 間隔（毫秒）

const CATEGORY_LABELS = {
  seo: "SEO",
  aeo: "AEO",
  geo: "GEO",
  security: "資安",
  ux: "UX",
};

// useInstallPrompt：取得 PWA 安裝能力。事件在 main.jsx 已全域捕捉到 window，
// 這裡讀回並監聽後續事件，避免「事件在元件掛載前觸發」的 race。
function isStandalone() {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    window.navigator.standalone === true
  );
}
function useInstallPrompt() {
  const [deferred, setDeferred] = useState(() => window.__argusInstallPrompt || null);
  const [installed, setInstalled] = useState(() => !!window.__argusInstalled || isStandalone());
  useEffect(() => {
    function onPrompt(e) {
      e.preventDefault();
      window.__argusInstallPrompt = e;
      setDeferred(e);
    }
    function onInstallable() {
      setDeferred(window.__argusInstallPrompt);
    }
    function onInstalled() {
      setInstalled(true);
      setDeferred(null);
    }
    // 掛載時若全域已捕捉到事件，立即採用（修正 race）
    if (window.__argusInstallPrompt) setDeferred(window.__argusInstallPrompt);
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("argus-installable", onInstallable);
    window.addEventListener("appinstalled", onInstalled);
    window.addEventListener("argus-installed", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("argus-installable", onInstallable);
      window.removeEventListener("appinstalled", onInstalled);
      window.removeEventListener("argus-installed", onInstalled);
    };
  }, []);
  async function trigger() {
    const d = deferred || window.__argusInstallPrompt;
    if (!d) return null;
    d.prompt();
    const { outcome } = await d.userChoice;
    window.__argusInstallPrompt = null;
    setDeferred(null);
    return outcome;
  }
  return { canInstall: !!deferred, installed, trigger };
}

export {
  CATEGORY_FILTERS,
  SEVERITY_FILTERS,
  STATUS_LABELS,
  IN_PROGRESS_STATUSES,
  isInProgress,
  SEVERITY_ORDER,
  SEVERITY_COLOR,
  SEVERITY_LABEL,
  CATEGORY_COLOR,
  CATEGORY_LABELS,
  apiErrorMessage,
  useDialogFocus,
  useConfirmDialogs,
  CountUp,
  StackedBar,
  SeverityBarChart,
  LineChart,
  useInstallPrompt,
};
