import { useEffect, useRef, useState } from "react";

const DEVICES = {
  desktop: { label: "桌面", width: 1280 },
  mobile: { label: "手機", width: 390 },
};
const MODES = [
  { key: "split", label: "並排比較" },
  { key: "original", label: "原始" },
  { key: "optimized", label: "優化後" },
];
// 預覽框在畫面上的高度（px）；iframe 依縮放比例放大高度，畫面上看起來固定這麼高
const VIEW_HEIGHT = 640;

/**
 * 以真實裝置寬度渲染頁面，再等比縮小放進容器：並排時兩邊仍是 1280px 的桌面版面，
 * 不會被擠成平板版面而看不出差別。
 *
 * sandbox 不給任何權限：HTML 來自受測網站，必須在獨立的 opaque origin 裡、
 * 不執行 script、不能送表單、不能導覽上層。
 */
function ScaledFrame({ html, title, deviceWidth }) {
  const boxRef = useRef(null);
  const [scale, setScale] = useState(1);

  useEffect(() => {
    const box = boxRef.current;
    if (!box) return undefined;
    const update = () => setScale(Math.min(1, box.clientWidth / deviceWidth));
    update();
    const observer = new ResizeObserver(update);
    observer.observe(box);
    return () => observer.disconnect();
  }, [deviceWidth]);

  return (
    <div className="opt-frame-box" ref={boxRef}>
      {html == null ? (
        <p className="opt-frame-empty">載入頁面中…</p>
      ) : (
        <iframe
          title={title}
          sandbox=""
          referrerPolicy="no-referrer"
          srcDoc={html}
          className="opt-frame"
          // 動態計算值：依容器寬度縮放
          style={{
            width: `${deviceWidth}px`,
            height: `${Math.round(VIEW_HEIGHT / scale)}px`,
            transform: `scale(${scale})`,
          }}
        />
      )}
    </div>
  );
}

/**
 * 原始／優化後的對照：並排、單看原始、單看優化後；桌面與手機寬度切換。
 * loadHtml(variant) 回傳 Promise<string>（擁有者走下載 API、分享頁走分享 API）。
 */
export default function ComparisonViewer({ loadHtml, hasOriginal, hasOptimized }) {
  const [mode, setMode] = useState(hasOriginal && hasOptimized ? "split" : "optimized");
  const [device, setDevice] = useState("desktop");
  const [docs, setDocs] = useState({});
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const variants = [hasOriginal && "original", hasOptimized && "optimized"].filter(Boolean);
    Promise.all(variants.map((variant) => loadHtml(variant).then((html) => [variant, html])))
      .then((pairs) => !cancelled && setDocs(Object.fromEntries(pairs)))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [loadHtml, hasOriginal, hasOptimized]);

  const panes =
    mode === "split"
      ? [["original", "原始頁面"], ["optimized", "Argus 優化後"]]
      : [[mode, mode === "original" ? "原始頁面" : "Argus 優化後"]];
  const width = DEVICES[device].width;

  return (
    <section className="opt-compare" aria-label="優化前後比較">
      <div className="opt-compare-bar">
        <div className="opt-segment" role="tablist" aria-label="比較方式">
          {MODES.filter((m) => m.key !== "split" || (hasOriginal && hasOptimized)).map((m) => (
            <button
              key={m.key}
              type="button"
              role="tab"
              aria-selected={mode === m.key}
              className={mode === m.key ? "is-active" : ""}
              disabled={(m.key === "original" && !hasOriginal) || (m.key === "optimized" && !hasOptimized)}
              onClick={() => setMode(m.key)}
            >
              {m.label}
            </button>
          ))}
        </div>
        <div className="opt-segment" role="tablist" aria-label="裝置寬度">
          {Object.entries(DEVICES).map(([key, item]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={device === key}
              className={device === key ? "is-active" : ""}
              onClick={() => setDevice(key)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>
      {failed ? (
        <p className="opt-frame-empty">無法載入頁面內容，檔案可能已被清理。</p>
      ) : (
        <div className={`opt-compare-panes ${panes.length > 1 ? "is-split" : ""} is-${device}`}>
          {panes.map(([variant, label]) => (
            <figure key={variant} className={`opt-pane is-${variant}`}>
              <figcaption>
                <span className={`opt-pane-tag is-${variant}`}>{variant === "original" ? "Before" : "After"}</span>
                {label}
              </figcaption>
              <ScaledFrame html={docs[variant]} title={label} deviceWidth={width} />
            </figure>
          ))}
        </div>
      )}
      <p className="opt-compare-note">
        預覽不執行網站的程式（JavaScript），輪播、彈出選單等互動功能可能不會動作；版面、文字與樣式的改變都看得到。
      </p>
    </section>
  );
}
