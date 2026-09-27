import { Link } from "react-router-dom";

import { useArgusStore } from "../../store";
import { ArgusMark } from "../../components/brand/ArgusMark";

// 未匹配路由。外層由 App.jsx 決定是否顯示登入後導覽列，這裡只畫內容，
// 所以不套 PublicLayout；給出回去的路與幾個常用入口，不留死路。

const SUGGESTIONS = [
  { to: "/verify", label: "報告查驗", desc: "輸入編號核對報告真偽" },
  { to: "/purchase", label: "方案與計費", desc: "按頁付費，點數永久有效" },
  { to: "/reviews", label: "使用者評論", desc: "看看其他人怎麼用 Argus" },
];

export default function NotFoundPage() {
  const accessToken = useArgusStore((state) => state.accessToken);
  return (
    <div className="public-shell notfound-shell">
      <section className="notfound">
        <div className="notfound-backdrop ag-surface-grid" aria-hidden="true" />
        <div className="notfound-scope ag-viewfinder" aria-hidden="true">
          <ArgusMark size={96} />
          <span className="notfound-code ag-num">404</span>
        </div>
        <span className="ag-eyebrow">404 · 找不到頁面</span>
        <h1 className="notfound-title">這個頁面不在守望範圍內</h1>
        <p className="notfound-sub">
          您嘗試訪問的網址不在 Argus 上，可能是連結已失效、輸入錯誤，或頁面已被移除。
        </p>
        <div className="notfound-actions">
          <Link to={accessToken ? "/dashboard" : "/project"} className="public-cta public-cta-primary">
            {accessToken ? "回 Dashboard" : "回首頁"}
          </Link>
          <Link to="/free-tools" className="public-cta public-cta-ghost">
            免費快速檢查
          </Link>
        </div>
        <ul className="notfound-links" aria-label="常用入口">
          {SUGGESTIONS.map((s) => (
            <li key={s.to}>
              <Link to={s.to}>
                <strong>{s.label}</strong>
                <span>{s.desc}</span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
