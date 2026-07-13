import { Link } from "react-router-dom";

import { useArgusStore } from "../../store";

export default function NotFoundPage() {
  const accessToken = useArgusStore((state) => state.accessToken);
  return (
    <div className="public-shell">
      <section className="public-hero">
        <div className="public-hero-content" style={{ textAlign: "center" }}>
          <span className="public-hero-eyebrow">404 · 找不到頁面</span>
          <h1 className="public-hero-title">
            這個頁面<span className="hero-grad">不存在</span>
          </h1>
          <p className="public-hero-sub">
            您嘗試訪問的網址不在 Argus 上，可能是連結已失效、輸入錯誤，或頁面已被移除。
          </p>
          <div
            style={{
              display: "flex",
              gap: "0.75rem",
              justifyContent: "center",
              flexWrap: "wrap",
              marginTop: "1.5rem",
            }}
          >
            <Link
              to={accessToken ? "/dashboard" : "/project"}
              className="public-cta-primary"
            >
              {accessToken ? "回 Dashboard" : "回首頁"}
            </Link>
            <Link to="/free-tools" className="public-cta-ghost">
              免費快速檢查
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
