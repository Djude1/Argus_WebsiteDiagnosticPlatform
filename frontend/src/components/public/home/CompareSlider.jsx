/**
 * 頁面優化前後對照（示意）：拖曳中間的把手（或用鍵盤左右鍵）露出更多原始頁面或優化後頁面。
 * 實際操作元件是一個透明的 range input 蓋在畫面上，拖曳、觸控與鍵盤都由瀏覽器原生處理。
 */
import { useState } from "react";

function MockPage({ variant }) {
  return (
    <div className={`hx-compare-page is-${variant}`} aria-hidden="true">
      <span className="hx-mock-nav" />
      <span className="hx-mock-hero" />
      <span className="hx-mock-title" />
      <span className="hx-mock-line" />
      <span className="hx-mock-line is-short" />
      <span className="hx-mock-cta" />
    </div>
  );
}

export default function CompareSlider() {
  const [split, setSplit] = useState(52);
  return (
    <div className="hx-preview hx-compare">
      <div className="hx-preview-bar">
        <span>頁面優化前後對照</span>
        <span className="hx-live-tag">示意</span>
      </div>
      <div className="hx-compare-stage" style={{ "--split": `${split}%` }}>
        <MockPage variant="after" />
        <div className="hx-compare-before">
          <MockPage variant="before" />
        </div>
        <span className="hx-compare-label is-before">原始頁面</span>
        <span className="hx-compare-label is-after">優化後</span>
        <span className="hx-compare-handle" aria-hidden="true" />
        <input
          type="range"
          min="5"
          max="95"
          value={split}
          onChange={(event) => setSplit(Number(event.target.value))}
          className="hx-compare-range"
          aria-label="拖曳比較原始頁面與優化後頁面"
        />
      </div>
    </div>
  );
}
