/**
 * 「掃描中」即時表格（示意）：每隔 1.5–4 秒在最上方插入一筆新的檢查，
 * 已有的列依「排隊中 → 檢查中 → 通過／找到問題」推進，最多保留 8 列（2026-10-09 起不再淡出最後幾列，避免看起來像載入失敗）。
 * 不在畫面內或偏好減少動態時停止更新，只顯示初始幾列的完成狀態。
 * 每一筆的檢查項目與問題名稱都對應 Argus 實際的規則。
 */
import { useEffect, useRef, useState } from "react";

import { useInView, usePrefersReducedMotion } from "./HomeMotion.jsx";

// result: pass＝通過；high／medium／low＝找到該嚴重度的問題
const CHECKS = [
  { page: "/", check: "HTTPS 與憑證", dim: "資安", result: "pass" },
  { page: "/", check: "缺少 Content-Security-Policy", dim: "資安", result: "medium" },
  { page: "/about", check: "圖片缺少替代文字", dim: "SEO", result: "low" },
  { page: "/pricing", check: "Title 與 description", dim: "SEO", result: "pass" },
  { page: "/faq", check: "營業時間能否找到答案", dim: "AEO", result: "pass" },
  { page: "/contact", check: "表單欄位沒有標籤", dim: "UX", result: "medium" },
  { page: "/blog/launch", check: "文章缺少作者標記", dim: "GEO", result: "low" },
  { page: "/products", check: "缺少結構化資料", dim: "GEO", result: "medium" },
  { page: "/login", check: "Cookie 缺少 Secure 旗標", dim: "資安", result: "medium" },
  { page: "/", check: "按鈕沒有可辨識的名稱", dim: "UX", result: "medium" },
  { page: "/news", check: "手機觸控目標", dim: "UX", result: "pass" },
  { page: "/", check: "SPF／DMARC 寄件驗證", dim: "資安", result: "pass" },
  { page: "/", check: "伺服器軟體版本含已知漏洞", dim: "資安", result: "high" },
  { page: "/about", check: "價格在兩頁寫法不同", dim: "AEO", result: "low" },
  { page: "/sitemap.xml", check: "sitemap 列出 noindex 頁", dim: "SEO", result: "low" },
];

const RESULT_LABEL = { high: "高", medium: "中", low: "低", pass: "通過" };
const MAX_ROWS = 8;
const SEED = 5;

function seedRows() {
  return CHECKS.slice(0, SEED).map((item, i) => ({
    ...item,
    id: `seed-${i}`,
    status: i === 0 ? "running" : "done",
  }));
}

// 排隊中有一半機會開始檢查；檢查中有 45% 機會完成
function advance(row) {
  if (row.status === "queued") return Math.random() < 0.5 ? { ...row, status: "running" } : row;
  if (row.status === "running") return Math.random() < 0.45 ? { ...row, status: "done" } : row;
  return row;
}

export default function LiveScanTable() {
  const [rows, setRows] = useState(seedRows);
  const cursor = useRef(SEED);
  const ref = useRef(null);
  const visible = useInView(ref);
  const reduced = usePrefersReducedMotion();
  const running = visible && !reduced;

  useEffect(() => {
    if (!running) return undefined;
    let timer;
    const tick = () => {
      setRows((prev) => {
        const item = CHECKS[cursor.current % CHECKS.length];
        cursor.current += 1;
        const fresh = { ...item, id: `row-${cursor.current}`, status: "queued", isNew: true };
        return [fresh, ...prev.map((row) => ({ ...advance(row), isNew: false }))].slice(0, MAX_ROWS);
      });
      timer = setTimeout(tick, 1500 + Math.random() * 2500);
    };
    timer = setTimeout(tick, 1200);
    return () => clearTimeout(timer);
  }, [running]);

  const shown = reduced ? rows.map((row) => ({ ...row, status: "done" })) : rows;

  return (
    <div ref={ref} className="hx-live">
      <div className="hx-live-bar">
        <span className="hx-live-url">example.com</span>
        <span className="hx-live-tag">示意</span>
      </div>
      <table className="hx-live-table">
        <thead>
          <tr>
            <th scope="col">頁面</th>
            <th scope="col">檢查項目</th>
            <th scope="col">面向</th>
            <th scope="col" className="is-right">結果</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((row) => (
            <tr key={row.id} className={row.isNew ? "is-new" : ""}>
              <td className="hx-live-page">{row.page}</td>
              <td className="hx-live-check">{row.check}</td>
              <td className="hx-live-dim">{row.dim}</td>
              <td className="is-right">
                {row.status === "queued" && <span className="hx-status is-queued">排隊中</span>}
                {row.status === "running" && <span className="hx-status is-running">檢查中</span>}
                {row.status === "done" && (
                  <span className={`hx-status is-${row.result}`}>{RESULT_LABEL[row.result]}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
