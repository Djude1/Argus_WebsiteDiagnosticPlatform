import { useCallback, useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate, useParams } from "react-router-dom";

import { api } from "../../api";
import PhishingResult from "../../components/public/PhishingResult.jsx";
import QuickScanResult from "../../components/public/QuickScanResult.jsx";
import SpeedTestResult from "../../components/public/SpeedTestResult.jsx";
import { useArgusStore } from "../../store";
import brandLogo from "../../assets/brand-logo.webp";
import argusEyeStill from "../../assets/argus-eye-still.webp";
import argusEye from "../../assets/argus-eye.webp";
import { HomeSections } from "../../components/public/home/HomeSections.jsx";
import { apiErrorMessage, useInstallPrompt } from "../../shared/AppShared.jsx";
import TechMarquee from "../../components/public/TechMarquee.jsx";
import SiteNav, { SiteThemeToggle } from "../../components/navigation/SiteNav.jsx";

const PUBLIC_NAV_ITEMS = [
  { to: "/project", label: "專案介紹" },
  { to: "/free-tools", label: "快速檢查" },
  { to: "/purchase", label: "購買" },
  { to: "/download", label: "下載" },
  { to: "/verify", label: "報告查驗" },
  { to: "/partners", label: "商業合作" },
  { to: "/reviews", label: "評論" },
];

function PublicNav() {
  const accessToken = useArgusStore((s) => s.accessToken);
  return (
    <SiteNav
      items={PUBLIC_NAV_ITEMS}
      actions={(
        <>
          <SiteThemeToggle />
          <NavLink to={accessToken ? "/dashboard" : "/login"} className="public-cta-primary">
            {accessToken ? "進入我的網站" : "登入 / 註冊"}
          </NavLink>
        </>
      )}
    />
  );
}

// 頁尾沿用改版後整理過的分組結構（產品／信任），視覺回到改版前的樣式。
const FOOTER_GROUPS = [
  {
    title: "產品",
    links: [
      { to: "/project", label: "專案介紹" },
      { to: "/free-tools", label: "免費快速檢查" },
      { to: "/purchase", label: "方案與計費" },
      { to: "/download", label: "下載 PWA" },
    ],
  },
  {
    title: "信任",
    links: [
      { to: "/verify", label: "報告查驗" },
      { to: "/reviews", label: "使用者評論" },
      { to: "/partners", label: "商業合作" },
      { to: "/scanner", label: "掃描來源說明" },
    ],
  },
  {
    title: "條款",
    links: [
      { to: "/privacy", label: "隱私權政策" },
      { to: "/terms", label: "服務條款" },
    ],
  },
];

function PublicFooter() {
  return (
    <footer className="public-footer">
      <div className="public-footer-inner">
        <div className="public-footer-about">
          <img src={brandLogo} className="public-footer-logo" alt="ARGUS" width="96" height="64" />
          <div className="public-footer-sub">網站健檢平台</div>
          <p className="public-footer-tagline">
            找出網站在 SEO、AEO、GEO、資安與使用體驗上的問題，附上證據並給出可直接套用的修正。
          </p>
        </div>
        <nav className="public-footer-groups" aria-label="頁尾導覽">
          {FOOTER_GROUPS.map((group) => (
            <div className="public-footer-group" key={group.title}>
              <h2 className="public-footer-group-title">{group.title}</h2>
              <ul>
                {group.links.map((link) => (
                  <li key={link.to}>
                    <NavLink to={link.to}>{link.label}</NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
        <div className="public-footer-copy">
          © Argus 網站健檢平台
        </div>
      </div>
    </footer>
  );
}

function PublicLayout() {
  return (
    <div className="public-shell">
      <PublicNav />
      <main className="public-main">
        <Outlet />
      </main>
      <PublicFooter />
    </div>
  );
}

// 每一項都對應 repo 內實際使用的技術（frontend/package.json、pyproject.toml、k8s/）。
const PROJECT_STACK_POINTS = [
  "前端 React 18 + Vite，逐步導入 TypeScript；後端 Django 5 + DRF",
  "Celery + Redis 排程，Playwright 驅動真實瀏覽器",
  "Docker 容器化，Argo CD 部署到 Kubernetes",
];


const HOME_FAQ = [
  {
    q: "快速檢查和完整掃描差在哪？",
    a: "快速檢查免登入、不扣點，只分析單一頁面的 HTML 與回應標頭；完整掃描會以真實瀏覽器爬取整站、逐頁截圖，產出互動報告與防偽 PDF 報告，還能針對單一頁面產出優化後的版本。",
  },
  {
    q: "完整掃描怎麼計費？",
    a: "按維度計費：每頁每維度 2 coin，只勾需要的維度就好。建立時依最大頁數預扣，完成後依實際頁數退回；掃描失敗或被取消會全額退回。註冊後第一次完整掃描（被動、整站、五個面向全選）免費，之後每月自動贈 200 coin。",
  },
  {
    q: "可以掃描不是我的網站嗎？",
    a: "只限你擁有或取得授權的網站。預設為被動模式，不做破壞性測試；要開啟主動式資安測試，必須先完成網域所有權驗證，所有操作都會記入稽核軌跡。",
  },
  {
    q: "收到的報告怎麼確認是真的？",
    a: "每份報告都有唯一編號與 SHA-256 指紋，任何人都能在「報告查驗」頁輸入編號核對，不需要登入。",
  },
];

function ProjectPage() {
  return (
    <div className="public-page">
      <section className="public-hero public-hero--console">
        <div className="public-hero-bg" aria-hidden="true">
          <span className="hero-orb hero-orb-1" />
          <span className="hero-orb hero-orb-2" />
          <span className="hero-orb hero-orb-3" />
          <span className="hero-grid" />
          <span className="hero-scan" />
          <span className="hero-corner tl" />
          <span className="hero-corner tr" />
          <span className="hero-corner bl" />
          <span className="hero-corner br" />
        </div>
        <div className="public-hero-content">
          {/* 品牌識別：會動的 Argus 之眼 ＋ 藝術字。
              之眼用 <picture>，偏好減少動態者自動換靜態首幀且不下載動態版。 */}
          <div className="public-hero-brand">
            <picture className="public-hero-eye">
              <source media="(prefers-reduced-motion: reduce)" srcSet={argusEyeStill} />
              <img src={argusEye} alt="" width="256" height="202" />
            </picture>
            <span className="public-hero-wordmark" aria-label="ARGUS">
              {"ARGUS".split("").map((ch, i) => (
                <span key={`${ch}-${i}`} style={{ animationDelay: `${i * 0.08}s` }}>{ch}</span>
              ))}
            </span>
          </div>
          <span className="public-hero-eyebrow">掃描 · 洞察 · 證據</span>
          <h1 className="public-hero-title">
            一鍵看見<span className="hero-grad">網站的所有問題</span>
          </h1>
          <p className="public-hero-sub">
            輸入網址，找出網站在<strong>搜尋、體驗與資安</strong>上的問題，並排好該先處理哪一個。
          </p>
          <p className="public-hero-sub is-highlight">
            不只列出問題——修正要用的檔案，直接生給你。
          </p>
          <div className="public-hero-actions">
            <NavLink to="/login" className="public-cta-primary">登入進行詳細檢查 →</NavLink>
            <NavLink to="/free-tools" className="public-cta-ghost">免登入先試單頁檢查</NavLink>
          </div>
        </div>
      </section>

      {/* hero 與技術棧之間的段落（2026-10-09 改版，見 components/public/home/） */}
      <HomeSections />

      <section className="project-stack">
        <div className="project-stack-intro">
          <p className="project-stack-eyebrow">技術棧</p>
          <h2 className="project-stack-title">全棧現代化選型</h2>
          <ul className="project-stack-points">
            {PROJECT_STACK_POINTS.map((point) => (
              <li key={point}>
                <span className="project-stack-dash" aria-hidden="true" />
                <p>{point}</p>
              </li>
            ))}
          </ul>
        </div>
        <TechMarquee />
      </section>

      <section className="public-section">
        <header className="public-section-head">
          <h2>常見問題</h2>
        </header>
        <div className="public-faq">
          {HOME_FAQ.map((item) => (
            <details key={item.q} className="public-faq-item">
              <summary>{item.q}</summary>
              <p>{item.a}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="public-section public-final-cta-wrap">
        <div className="public-final-cta">
          <div>
            <h2 className="public-final-cta-title">準備好健檢你的網站了嗎？</h2>
            <p className="public-final-cta-sub">註冊後第一次完整掃描免費，之後每月贈 200 coin；也可先用免登入的「快速檢查」。</p>
          </div>
          <NavLink to="/purchase" className="public-cta-primary public-final-cta-btn">
            查看方案 →
          </NavLink>
        </div>
      </section>
    </div>
  );
}

const PURCHASE_FAQ = [
  {
    q: "點數會過期嗎？",
    a: "不會。已購點數永久有效，未使用的點數可一直累積。",
  },
  {
    q: "如何計算所需點數？",
    a: "掃描按維度計費：每頁每維度 2 coin，只勾需要的維度即省費用（五維全選＝每頁 10 coin）。建立時依「最大頁數」預扣，完成後依實際頁數退回未使用的部分。",
  },
  {
    q: "支援哪些付款方式？",
    a: "信用卡付款由綠界科技處理：購點送出訂單後導向綠界付款頁，付款完成由綠界回傳通知後才會入點；月訂閱以綠界信用卡定期定額每月自動扣款，可隨時取消。電子發票依你填寫的資料開立並寄至 Email。",
  },
  {
    q: "可以退費嗎？",
    a: "如有特殊狀況請聯絡管理員，由 admin 在後台手動退費。掃描失敗或被取消時，系統會自動全額退回預扣的點數。",
  },
];

const COMPARE_ROWS = [
  {
    feature: "全站爬蟲（同網域、深度 3、最多 50 頁）",
    argus: true, self: "技術門檻高", competitor: "通常另計",
  },
  {
    feature: "SEO + AEO + GEO + 資安四維掃描",
    argus: true, self: "工具多套需自己整合", competitor: "多為單一維度",
  },
  {
    feature: "AI Agent 擬真使用者 UX 測試",
    argus: true, self: "無", competitor: "罕見",
  },
  {
    feature: "可互動報告（截圖紅框 + 雙向跳轉）",
    argus: true, self: "Lighthouse 純文字", competitor: "PDF 為主",
  },
  {
    feature: "PDF 報告自動匯出",
    argus: true, self: "手寫", competitor: "額外加購",
  },
  {
    feature: "結構化問題 Prompt 帶去 ChatGPT 修",
    argus: true, self: "需要自己整理", competitor: "—",
  },
  {
    feature: "按頁付費（用多少付多少）",
    argus: true, self: "—", competitor: "月費綁約",
  },
  {
    feature: "首月免費 200 coin",
    argus: true, self: "—", competitor: "需信用卡綁定試用",
  },
];

function PurchasePage() {
  const [openFaq, setOpenFaq] = useState(0);
  const navigate = useNavigate();
  return (
    <div className="public-page">
      <section className="public-hero compact">
        <div className="public-hero-bg" aria-hidden="true">
          <span className="hero-orb hero-orb-1" />
          <span className="hero-orb hero-orb-2" />
          <span className="hero-orb hero-orb-3" />
        </div>
        <div className="public-hero-content">
          <span className="public-hero-eyebrow">PRICING · 為什麼選 Argus</span>
          <h1 className="public-hero-title">
            <span className="hero-grad">按頁付費</span>，永久有效
          </h1>
          <p className="public-hero-sub">
            掃描按維度計費，每頁每維度 2 coin、只勾選需要的項目；新會員每月自動贈送 200 coin；買越多越划算，
            點數不會過期，失敗或取消自動全額退回。
          </p>
          <div className="public-hero-actions">
            <button
              type="button"
              className="public-cta-primary"
              onClick={() => navigate("/billing")}
            >
              看方案 + 開始結帳 →
            </button>
          </div>
        </div>
      </section>

      <section className="public-section">
        <header className="public-section-head">
          <h2>為什麼選 Argus</h2>
          <p>Argus、自己做、市面工具，三者比一比</p>
        </header>
        <div className="public-compare-wrap">
          <table className="public-compare-table">
            <thead>
              <tr>
                <th className="public-compare-feature">功能</th>
                <th className="public-compare-argus">
                  <div className="public-compare-brand">⟡ ARGUS</div>
                </th>
                <th>自己做</th>
                <th>競品工具</th>
              </tr>
            </thead>
            <tbody>
              {COMPARE_ROWS.map((row, idx) => (
                <tr key={idx}>
                  <td className="public-compare-feature">{row.feature}</td>
                  <td className="public-compare-argus">
                    {row.argus === true ? <span className="check-yes">✓</span> : row.argus}
                  </td>
                  <td className="public-compare-cell">{row.self}</td>
                  <td className="public-compare-cell">{row.competitor}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="public-section">
        <header className="public-section-head">
          <h2>常見問題</h2>
        </header>
        <div className="public-faq">
          {PURCHASE_FAQ.map((item, idx) => (
            <details
              key={idx}
              open={openFaq === idx}
              onToggle={(e) => e.target.open && setOpenFaq(idx)}
              className="public-faq-item"
            >
              <summary>{item.q}</summary>
              <p>{item.a}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="public-section public-final-cta-wrap">
        <div className="public-final-cta">
          <div>
            <h2 className="public-final-cta-title">準備好了嗎？</h2>
            <p className="public-final-cta-sub">3 步驟結帳，30 秒入帳，馬上開始健檢你的網站。</p>
          </div>
          <button
            type="button"
            className="public-cta-primary public-final-cta-btn"
            onClick={() => navigate("/billing")}
          >
            前往結帳 →
          </button>
        </div>
      </section>

    </div>
  );
}

function useInsightTool(endpoint) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const run = async (payload, fallbackMessage) => {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const res = await api.post(endpoint, payload);
      setResult(res.data);
    } catch (err) {
      setError(apiErrorMessage(err, fallbackMessage));
    } finally {
      setLoading(false);
    }
  };
  return { loading, result, error, run };
}

function FreeToolsPage() {
  // 導流 CTA「登入建立完整掃描」要用；先前漏宣告，按鈕點了會丟 ReferenceError
  const navigate = useNavigate();
  const [speedForm, setSpeedForm] = useState({
    url: "",
    authorization_confirmed: false,
  });
  const [urlValue, setUrlValue] = useState("");
  const [emailValue, setEmailValue] = useState("");
  const [quickForm, setQuickForm] = useState({ url: "", authorization_confirmed: false });
  const [tool, setTool] = useState("scan"); // 免費工具分頁：scan / speed / phish

  const speed = useInsightTool("/insights/speed-test/");
  const quick = useInsightTool("/insights/quick-scan/");
  const urlCheck = useInsightTool("/insights/phishing-url/");
  const emailCheck = useInsightTool("/insights/phishing-email/");

  const runSpeedTest = (event) => {
    event.preventDefault();
    speed.run(speedForm, "測速失敗，請確認網址可公開連線。");
  };

  const runQuickScan = (event) => {
    event.preventDefault();
    quick.run(quickForm, "單頁快速檢查失敗，請確認網址可公開連線。");
  };

  const runUrlCheck = (event) => {
    event.preventDefault();
    urlCheck.run({ url: urlValue }, "URL 風險分析失敗。");
  };

  const runEmailCheck = (event) => {
    event.preventDefault();
    emailCheck.run({ raw_email: emailValue }, "郵件風險分析失敗。");
  };

  return (
    <div className="public-page free-tools-page">
      <section className="public-hero compact">
        <div className="public-hero-bg" aria-hidden="true">
          <span className="hero-orb hero-orb-1" />
          <span className="hero-orb hero-orb-2" />
          <span className="hero-orb hero-orb-3" />
        </div>
        <div className="public-hero-content">
          <span className="public-hero-eyebrow">QUICK CHECK · 快速檢查</span>
          <h1 className="public-hero-title">
            先用<span className="hero-grad">快速檢查</span>初步判斷
          </h1>
          <p className="public-hero-sub">
            <strong>免登入、不扣點數、即時出結果。</strong>網站測速除了 Argus 的輕量量測，也會串接 Google PageSpeed Insights；
            釣魚網址與郵件判斷使用本機特徵分類器，不把內容送到大模型 API。
          </p>
        </div>
      </section>

      <div className="insight-tabs">
        <button type="button" className={`insight-tab ${tool === "scan" ? "active" : ""}`} onClick={() => setTool("scan")}>🩺 單頁檢查</button>
        <button type="button" className={`insight-tab ${tool === "speed" ? "active" : ""}`} onClick={() => setTool("speed")}>⚡ 網站測速</button>
        <button type="button" className={`insight-tab ${tool === "phish" ? "active" : ""}`} onClick={() => setTool("phish")}>🛡️ 釣魚偵測</button>
      </div>

      {tool === "scan" && (
      <section className="public-section">
        <header className="public-section-head">
          <h2>單頁快速檢查</h2>
          <p>輸入一個網址，立即看這一頁的 SEO、資安與 AEO／GEO 分數與重點問題；整站檢查請登入後建立完整掃描</p>
        </header>
        <form className="speed-form" onSubmit={runQuickScan}>
          <div className="speed-form-row">
            <label className="speed-form-field">
              <span>網址</span>
              <input
                value={quickForm.url}
                onChange={(e) => setQuickForm((f) => ({ ...f, url: e.target.value }))}
                placeholder="https://example.com/"
                required
              />
            </label>
            <button type="submit" className="public-cta-primary" disabled={quick.loading}>
              {quick.loading ? "檢查中..." : "開始單頁檢查"}
            </button>
          </div>
          <label className="insight-check">
            <input
              type="checkbox"
              checked={quickForm.authorization_confirmed}
              onChange={(e) => setQuickForm((f) => ({ ...f, authorization_confirmed: e.target.checked }))}
            />
            <span>我確認此頁面可公開檢測，或我擁有分析授權。</span>
          </label>
          {quick.error && <div className="insight-error">{quick.error}</div>}
        </form>
        {quick.result ? (
          <QuickScanResult result={quick.result} onFullScan={() => navigate("/login")} />
        ) : (
          <p className="speed-hint">會輸出：整體分數與等級、SEO／資安／AEO·GEO 三個面向的分數，以及依嚴重度排序的問題清單。</p>
        )}
      </section>
      )}

      {tool === "speed" && (
      <section className="public-section">
        <header className="public-section-head">
          <h2>網站測速分析</h2>
          <p>單一 URL、單次請求，不扣 coin，不啟動全站爬蟲</p>
        </header>
        <form className="speed-form" onSubmit={runSpeedTest}>
          <div className="speed-form-row">
            <label className="speed-form-field">
              <span>網址</span>
              <input
                value={speedForm.url}
                onChange={(e) => setSpeedForm((f) => ({ ...f, url: e.target.value }))}
                placeholder="https://example.com/"
                required
              />
            </label>
            <button type="submit" className="public-cta-primary" disabled={speed.loading}>
              {speed.loading ? "測速中..." : "開始測速"}
            </button>
          </div>
          <label className="insight-check">
            <input
              type="checkbox"
              checked={speedForm.authorization_confirmed}
              onChange={(e) => setSpeedForm((f) => ({ ...f, authorization_confirmed: e.target.checked }))}
            />
            <span>我確認此頁面可公開測速，或我擁有分析授權。</span>
          </label>
          {speed.error && <div className="insight-error">{speed.error}</div>}
        </form>
        {speed.result ? (
          <SpeedTestResult result={speed.result} />
        ) : (
          <p className="speed-hint">
            會輸出：Argus 測速分數、伺服器回應時間、傳輸量、阻塞 script 與圖片延遲載入等檢查；
            平台啟用時另附 Google PageSpeed Insights 的 Lighthouse 分數與 Chrome 真實使用者資料。
          </p>
        )}
      </section>
      )}

      {tool === "phish" && (
      <section className="public-section">
        <header className="public-section-head">
          <h2>可疑網址 / 詐騙郵件檢測</h2>
          <p>貼上一個網址或一封郵件內容，本機特徵分類器幫你判斷「是否可能是釣魚／詐騙」（不外送大模型 API）</p>
        </header>
        <div className="phish-grid">
          <section className="speed-panel">
            <header className="speed-panel-head">
              <h3>網址安全檢測</h3>
              <span className="speed-tag">防釣魚連結</span>
            </header>
            <form className="phish-form" onSubmit={runUrlCheck}>
              <label className="speed-form-field">
                <span>可疑連結</span>
                <input
                  value={urlValue}
                  onChange={(e) => setUrlValue(e.target.value)}
                  placeholder="https://secure-login.example/verify"
                  required
                />
              </label>
              {urlCheck.error && <div className="insight-error">{urlCheck.error}</div>}
              <button type="submit" className="public-cta-primary" disabled={urlCheck.loading}>
                {urlCheck.loading ? "分析中..." : "分析網址"}
              </button>
            </form>
            {urlCheck.result && <PhishingResult result={urlCheck.result} />}
          </section>

          <section className="speed-panel">
            <header className="speed-panel-head">
              <h3>郵件詐騙檢測</h3>
              <span className="speed-tag">防釣魚信</span>
            </header>
            <form className="phish-form" onSubmit={runEmailCheck}>
              <label className="speed-form-field">
                <span>原始信件內容（含標頭，可從郵件軟體「顯示原始碼」複製）</span>
                <textarea
                  value={emailValue}
                  onChange={(e) => setEmailValue(e.target.value)}
                  placeholder={"From: notice@example.com\nAuthentication-Results: ...\n\n請立即驗證帳號..."}
                  rows={8}
                  required
                />
              </label>
              {emailCheck.error && <div className="insight-error">{emailCheck.error}</div>}
              <button type="submit" className="public-cta-primary" disabled={emailCheck.loading}>
                {emailCheck.loading ? "分析中..." : "分析郵件"}
              </button>
            </form>
            {emailCheck.result && <PhishingResult result={emailCheck.result} email />}
          </section>
        </div>
      </section>
      )}
    </div>
  );
}

function formatDateTime(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}


function VerifyReportPage() {
  // 讀者可能是「收到 PDF 報告的第三方」而不是 Argus 使用者：網址帶編號就直接查，
  // 沒帶就給輸入框讓他照著報告封面上的編號輸入。
  const { reportNumber: routeNumber } = useParams();
  const [input, setInput] = useState(routeNumber || "");
  const [state, setState] = useState({ loading: false, data: null, error: "" });

  const lookup = useCallback(async (number) => {
    const trimmed = (number || "").trim().toUpperCase();
    if (!trimmed) return;
    setState({ loading: true, data: null, error: "" });
    try {
      const res = await api.get(`/verify/${encodeURIComponent(trimmed)}/`);
      setState({ loading: false, data: res.data, error: "" });
    } catch (err) {
      setState({
        loading: false,
        data: null,
        error: apiErrorMessage(err, "查驗失敗，請稍後再試。"),
      });
    }
  }, []);

  useEffect(() => {
    if (routeNumber) lookup(routeNumber);
  }, [routeNumber, lookup]);

  return (
    <div className="public-page">
      <section className="public-hero">
        <div className="public-hero-bg" aria-hidden="true">
          <span className="hero-orb hero-orb-1" />
          <span className="hero-orb hero-orb-2" />
        </div>
        <div className="public-hero-content">
          <span className="public-hero-eyebrow">VERIFY · 報告查驗</span>
          <h1 className="public-hero-title">
            核對<span className="hero-grad">報告真偽</span>
          </h1>
          <p className="public-hero-sub">
            收到一份 Argus 網站健檢報告？輸入封面上的報告編號，即可核對它確實由 Argus
            出具，以及當初掃描的目標與時間。查驗不需要登入。
          </p>
        </div>
      </section>

      <section className="public-section">
        <div className="verify-layout">
          <form
            className="insight-tool-card"
            onSubmit={(e) => {
              e.preventDefault();
              lookup(input);
            }}
          >
            <h3 className="insight-card-title">輸入報告編號</h3>
            <label className="insight-field">
              <span>報告編號（在報告封面與每頁頁尾）</span>
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="ARGUS-28-20260831-A1B2"
                autoComplete="off"
                required
              />
            </label>
            <button
              type="submit"
              className="public-cta-primary"
              disabled={state.loading}
            >
              {state.loading ? "查驗中…" : "查驗報告"}
            </button>

            {state.error && (
              <div className="verify-result verify-result-fail">
                <div className="verify-result-head">查無此編號</div>
                <p>{state.error}</p>
                <p className="verify-result-note">
                  這份報告可能不是由 Argus 出具，或編號輸入有誤。請對照報告封面重新輸入。
                </p>
              </div>
            )}

            {state.data && (
              <div className="verify-result verify-result-pass">
                <div className="verify-result-head">✓ 這是一份由 Argus 出具的報告</div>
                <dl className="verify-facts">
                  <dt>報告編號</dt>
                  <dd>{state.data.report_number}</dd>
                  <dt>掃描目標</dt>
                  <dd>{state.data.scan_target}</dd>
                  <dt>掃描完成</dt>
                  <dd>{formatDateTime(state.data.scanned_at)}</dd>
                  <dt>報告產生</dt>
                  <dd>{formatDateTime(state.data.generated_at)}</dd>
                  <dt>整體分數</dt>
                  <dd>
                    {state.data.overall_score === null
                      ? "尚未產生"
                      : `${state.data.overall_score} / 100`}
                  </dd>
                </dl>
                <p className="verify-result-note">
                  請核對上列資訊與你手上的報告是否一致。若要進一步確認檔案未被竄改，
                  可自行計算該 PDF 的 SHA-256 並與下方指紋比對。
                </p>
                <code className="verify-fingerprint">{state.data.content_sha256}</code>
              </div>
            )}
          </form>

          <aside className="verify-aside">
            <h3 className="insight-card-title">查驗能證明什麼</h3>
            <ul className="verify-aside-list">
              <li>
                <strong>編號存在</strong>
                <span>代表 Argus 確實為這個網站產生過報告。</span>
              </li>
              <li>
                <strong>目標與時間</strong>
                <span>核對報告封面寫的網址與掃描時間是否被改過。</span>
              </li>
              <li>
                <strong>內容指紋</strong>
                <span>比對 SHA-256 可確認整份檔案一個字都沒被動過。</span>
              </li>
            </ul>
            <p className="verify-aside-note">
              查驗結果不會顯示是誰執行的掃描。
            </p>
          </aside>
        </div>
      </section>
    </div>
  );
}


function DownloadPage() {
  const [releases, setReleases] = useState([]);
  const { canInstall, installed, trigger } = useInstallPrompt();
  useEffect(() => {
    api.get("/content/releases/").then((r) => setReleases(r.data.releases || [])).catch(() => {});
  }, []);
  const latest = releases.find((r) => r.is_latest) || releases[0];
  return (
    <div className="public-page">
      <section className="public-hero">
        <div className="public-hero-bg" aria-hidden="true">
          <span className="hero-orb hero-orb-1" />
          <span className="hero-orb hero-orb-2" />
        </div>
        <div className="public-hero-content">
          <span className="public-hero-eyebrow">DOWNLOAD · 下載安裝</span>
          <h1 className="public-hero-title">
            <span className="hero-grad">隨身</span>使用 Argus
          </h1>
          <p className="public-hero-sub">
            Argus 是 PWA（漸進式網頁應用），無需透過 App Store — 直接從瀏覽器加到主畫面，像 App 一樣開啟，支援離線瀏覽既有報告。
          </p>
          <div className="public-hero-actions">
            {installed ? (
              <span className="public-install-installed">✓ 已安裝，請從主畫面開啟</span>
            ) : (
              <button
                type="button"
                className="public-cta-primary public-install-cta"
                onClick={async () => {
                  if (canInstall) {
                    await trigger();
                  } else {
                    // 瀏覽器尚未提供安裝（如 iOS Safari 不支援程式化安裝，或事件未就緒）
                    // → 帶到各平台安裝步驟
                    document
                      .getElementById("install-guide")
                      ?.scrollIntoView({ behavior: "smooth" });
                  }
                }}
              >
                ⬇ 點擊下載
              </button>
            )}
            {!installed && latest?.download_url && (
              <a className="public-cta-ghost" href={latest.download_url}>
                取得 {latest.platform_label} 版 →
              </a>
            )}
          </div>
        </div>
      </section>

      <section className="public-section" id="install-guide">
        <header className="public-section-head">
          <h2>安裝步驟</h2>
          <p>三大平台一覽</p>
        </header>
        <div className="public-install-grid">
          <div className="public-install-card">
            <div className="public-install-icon">💻</div>
            <div className="public-install-title">桌面（Chrome / Edge）</div>
            <ol>
              <li>網址列右側點選安裝圖示 <kbd>⬇</kbd></li>
              <li>點「安裝」即出現桌面捷徑</li>
            </ol>
          </div>
          <div className="public-install-card">
            <div className="public-install-icon">🤖</div>
            <div className="public-install-title">Android（Chrome）</div>
            <ol>
              <li>右上 ⋮ 選單 → 「加到主畫面」</li>
              <li>確認 → 出現於主畫面</li>
            </ol>
          </div>
          <div className="public-install-card">
            <div className="public-install-icon">🍎</div>
            <div className="public-install-title">iOS（Safari）</div>
            <ol>
              <li>下方分享按鈕 → 「加入主畫面」</li>
              <li>確認 → 出現於主畫面</li>
            </ol>
          </div>
        </div>
      </section>

      {latest && (
        <section className="public-section">
          <header className="public-section-head">
            <h2>版本資訊</h2>
            <p>最新版 {latest.version}（{latest.platform_label}）</p>
          </header>
          <div className="public-release-card">
            <div className="public-release-version">
              <span className="public-release-badge">最新</span>
              v{latest.version}
            </div>
            <div className="public-release-date">
              {new Date(latest.released_at).toLocaleDateString("zh-Hant")}
            </div>
            <p className="public-release-notes">{latest.release_notes}</p>
            {latest.download_url && (
              <a className="public-cta-primary" href={latest.download_url}>
                ⬇ 取得 {latest.platform_label}
              </a>
            )}
          </div>

          {releases.length > 1 && (
            <details className="public-release-history">
              <summary>查看歷史版本</summary>
              <ul>
                {releases.slice(1).map((r) => (
                  <li key={r.id}>
                    <strong>v{r.version}</strong>
                    <span className="public-release-history-date">
                      {new Date(r.released_at).toLocaleDateString("zh-Hant")}
                    </span>
                    <span>{r.release_notes}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </section>
      )}
    </div>
  );
}

// ============================================================
// /admin React 後台（精簡 5 大分類 + dark cyan 主題）
// 走獨立 layout，不顯示前台 TopNav；只有 is_staff 可進入。
// ============================================================

export {
  PublicLayout,
  ProjectPage,
  PurchasePage,
  FreeToolsPage,
  DownloadPage,
  VerifyReportPage,
};
