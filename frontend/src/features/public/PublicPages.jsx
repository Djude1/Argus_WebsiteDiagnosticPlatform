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
import PageLoader from "../../shared/PageLoader.jsx";
import {
  CheckCircleIcon,
  ClockIcon,
  CoinIcon,
  DownloadIcon,
  GaugeIcon,
  MonitorIcon,
  MoreIcon,
  ScoreIcon,
  ShareIcon,
  ShieldIcon,
  SparkIcon,
} from "../../shared/LineIcons.jsx";

const PUBLIC_NAV_ITEMS = [
  { to: "/project", label: "專案介紹" },
  { to: "/free-tools", label: "快速檢查" },
  { to: "/purchase", label: "方案" },
  { to: "/verify", label: "報告查驗" },
  { to: "/partners", label: "商業合作" },
  { to: "/reviews", label: "評論" },
  { to: "/download", label: "下載" },
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
          <div className="public-footer-sub">AI網站健檢平台</div>
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
          © Argus AI網站健檢平台
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
  {
    q: "為什麼 JavaScript 動態載入的內容不會被檢測？",
    a: "因為稽核主要模擬搜尋引擎與 AI 爬蟲直接透過 HTTP 取得網頁原始內容的情境，不會像完整瀏覽器一樣執行 JavaScript 並等待動態內容載入。如果重要文字、FAQ、產品資訊或結構化內容只有在 JavaScript 執行後才出現，部分搜尋引擎或 AI 爬蟲可能無法穩定取得這些資訊。因此，這類內容未被檢測到時，往往也代表網站在 SEO、AEO 或 GEO 上可能存在可見性風險。",
  },
  {
    q: "掃描會不會影響或拖慢我的網站？",
    a: "預設的被動模式只讀取頁面、不做任何破壞性操作，且請求有速率限制，正常網站幾乎不會有感。只有在你完成網域驗證、主動開啟的主動式資安測試才會送出探測性請求，而這也受範圍與授權層層控制。",
  },
  {
    q: "分數是怎麼算出來的？是業界標準嗎？",
    a: "分數是 Argus 自訂的模型、不是官方或業界標準：每個面向從 100 分起算，依發現問題的嚴重度與數量以指數方式衰減。報告與「分數說明」會逐項列出扣了多少、為什麼，你可以自己加總核對，不是一個黑盒數字。",
  },
  {
    q: "為什麼有些項目顯示「未評估」？",
    a: "當某項檢查沒有跑完、被網站阻擋，或內容太少不足以判斷時，我們寧可標示「未評估」也不會假裝「沒問題」。這代表這次無法下結論、不等於安全或滿分；你可以針對該面向重新掃描或補齊內容後再看。",
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

// 方案與計費頁（/purchase，2026-10-10 依現行計費改寫）。
// 計費規則以 apps/billing/CLAUDE.md 為準：每頁每面向 2 點、首次完整掃描免費、每月贈點、
// AI 擬真 UX 測試與深度資安附加費；點數包與月訂閱的價格一律讀公開 API，不寫死在前端。
const BILLING_RULES = [
  {
    Icon: SparkIcon,
    title: "第一次完整掃描免費",
    desc: "註冊後第一次「被動、全網站、五個面向全選」的完整掃描（最多 50 頁，含 AI 擬真使用者測試）不扣點；掃描失敗或取消不算用掉。",
  },
  {
    Icon: CoinIcon,
    title: "依頁數 × 面向計費",
    desc: "每頁每個面向 2 點，只勾需要的面向（五個全選＝每頁 10 點）。建立時依頁數上限預扣，完成後依實際掃到的頁數退回差額。",
  },
  {
    Icon: CheckCircleIcon,
    title: "失敗或取消全額退回",
    desc: "掃描失敗、無法連線或你主動取消，預扣的點數自動全額退回；購買的點數不會過期。",
  },
];

const COST_EXAMPLES = [
  { scope: "單一頁面，五個面向", calc: "1 頁 × 5 面向 × 2 點", total: "10 點" },
  { scope: "全網站 20 頁，只看 SEO 與 GEO", calc: "20 頁 × 2 面向 × 2 點", total: "80 點" },
  { scope: "全網站 50 頁，五個面向", calc: "50 頁 × 5 面向 × 2 點 ＋ AI 擬真使用者測試 20 點", total: "520 點" },
  { scope: "再加主動式深度資安測試", calc: "需先完成網域驗證；AI 資安專家沒有實際執行就退回", total: "＋50 點" },
];

const PURCHASE_FAQ = [
  {
    q: "點數會過期嗎？",
    a: "購買與訂閱取得的點數不會過期，未用完可以一直累積。",
  },
  {
    q: "每月贈點是怎麼給的？",
    a: "會員每月自動獲得 200 點。還沒有購點或訂閱過的帳號，贈點只會把餘額補到 600 點為止；購點或訂閱後就沒有這個上限。",
  },
  {
    q: "點數包和月訂閱差在哪？",
    a: "點數包是一次付清、立即入點，適合偶爾掃描；月訂閱以信用卡每月自動扣款、每期開始時發放點數，單價較低，適合定期巡檢，可隨時取消，已開始的當期點數照樣保留。",
  },
  {
    q: "支援哪些付款方式？會開發票嗎？",
    a: "信用卡付款由綠界科技處理，付款完成並由綠界回傳通知後才會入點。電子發票依你結帳時填寫的資料開立並寄到 Email。",
  },
  {
    q: "可以退費嗎？",
    a: "掃描失敗或取消時系統會自動退回點數。已購買點數如有特殊狀況需要退費，請透過商業合作頁或客服聯絡我們，由管理員協助處理。",
  },
];

const COMPARE_ROWS = [
  { feature: "全網站爬取（同網域、最多 50 頁，依 sitemap 補齊頁面）", self: "技術門檻高", competitor: "通常另計" },
  { feature: "SEO、AEO、GEO、使用體驗、資安五個面向一次檢查", self: "多套工具自己整合", competitor: "多為單一面向" },
  { feature: "AI 擬真使用者操作網站的使用體驗測試", self: "無", competitor: "罕見" },
  { feature: "互動報告：截圖框出問題元素、逐項附證據", self: "Lighthouse 文字報告", competitor: "以 PDF 為主" },
  { feature: "PDF 報告與公開防偽查驗", self: "需自行整理", competitor: "常需加購" },
  { feature: "依頁數與面向計費，點數不過期", self: "—", competitor: "月費綁約" },
  { feature: "第一次完整掃描免費", self: "—", competitor: "需綁信用卡試用" },
];

function formatNtd(value) {
  return `NT$ ${Number(value || 0).toLocaleString("zh-Hant")}`;
}

function formatCoins(value) {
  return `${Number(value || 0).toLocaleString("zh-Hant")} 點`;
}

// 公開方案清單：點數包（/billing/plans/）與月訂閱（/billing/subscription/plans/）
function usePublicPlans() {
  const [state, setState] = useState({ loading: true, error: "", packs: [], subs: [], payEnabled: true });
  const load = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: "" }));
    Promise.all([api.get("/billing/plans/"), api.get("/billing/subscription/plans/")])
      .then(([packs, subs]) =>
        setState({
          loading: false,
          error: "",
          packs: packs.data.plans || [],
          subs: subs.data.plans || [],
          payEnabled: Boolean(packs.data.purchase_enabled),
        }),
      )
      .catch(() => setState((s) => ({ ...s, loading: false, error: "方案載入失敗，請稍後重新整理。" })));
  }, []);
  useEffect(() => {
    load();
  }, [load]);
  return { ...state, reload: load };
}

function PurchasePage() {
  const accessToken = useArgusStore((s) => s.accessToken);
  const plans = usePublicPlans();
  // 結帳在會員區 /billing；未登入先登入再回到結帳
  const checkoutTo = accessToken ? "/billing" : `/login?next=${encodeURIComponent("/billing")}`;
  const planCta = accessToken ? "前往結帳" : "登入後購買";

  return (
    <div className="public-page pricing-page">
      <section className="public-hero compact">
        <div className="public-hero-bg" aria-hidden="true">
          <span className="hero-orb hero-orb-1" />
          <span className="hero-orb hero-orb-2" />
          <span className="hero-orb hero-orb-3" />
        </div>
        <div className="public-hero-content">
          <span className="public-hero-eyebrow">PRICING · 方案與計費</span>
          <h1 className="public-hero-title">
            先<span className="hero-grad">免費掃一次</span>
          </h1>
          <p className="public-hero-sub">
            看完報告再決定怎麼付。之後依「頁數 × 面向」用點數計費，用多少扣多少；失敗或取消全額退回，點數不會過期。
          </p>
          <div className="public-hero-actions">
            <NavLink to={accessToken ? "/projects" : "/login?tab=register"} className="public-cta-primary">
              {accessToken ? "開始掃描" : "免費註冊並掃描"}
            </NavLink>
            <a className="public-cta-ghost" href="#plans">看方案價格</a>
          </div>
        </div>
      </section>

      <section className="public-section">
        <header className="public-section-head">
          <h2>怎麼計費</h2>
          <p>三件事就能算清楚，沒有月費綁約。</p>
        </header>
        <ul className="pub-card-grid">
          {BILLING_RULES.map(({ Icon, title, desc }) => (
            <li key={title} className="pub-card">
              <span className="hx-icon-box"><Icon /></span>
              <h3>{title}</h3>
              <p>{desc}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="public-section">
        <header className="public-section-head">
          <h2>試算範例</h2>
          <p>建立掃描時會先顯示預估點數，確認後才送出。</p>
        </header>
        <div className="pricing-table-wrap">
          <table className="pricing-table">
            <thead>
              <tr>
                <th scope="col">掃描內容</th>
                <th scope="col">算法</th>
                <th scope="col">點數</th>
              </tr>
            </thead>
            <tbody>
              {COST_EXAMPLES.map((row) => (
                <tr key={row.scope}>
                  <th scope="row">{row.scope}</th>
                  <td>{row.calc}</td>
                  <td className="pricing-table-total">{row.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="pricing-note">
          AI 擬真使用者測試只在全網站且勾選使用體驗時收取；若實際只掃到 1 頁會自動退回。以上為平台目前的計費單價。
        </p>
      </section>

      <section className="public-section" id="plans">
        <header className="public-section-head">
          <h2>方案價格</h2>
          <p>偶爾掃描買點數包；定期巡檢用月訂閱，單價更低。</p>
        </header>

        {!plans.loading && !plans.error && !plans.payEnabled && (
          <p className="pricing-banner">線上付款目前尚未開放，以下為參考價格；需要點數請透過「商業合作」與我們聯絡。</p>
        )}
        {plans.loading && <PageLoader label="載入方案中…" />}
        {plans.error && (
          <p className="pricing-banner">
            {plans.error}
            <button type="button" className="pricing-retry" onClick={plans.reload}>重新載入</button>
          </p>
        )}

        {plans.subs.length > 0 && (
          <>
            <h3 className="pricing-group-title">月訂閱</h3>
            <ul className="pricing-plans">
              {plans.subs.map((plan) => (
                <li key={plan.code} className={`pub-card pricing-plan ${plan.badge ? "is-featured" : ""}`}>
                  <div className="pricing-plan-head">
                    <h4>{plan.name}</h4>
                    {plan.badge && <span className="pricing-badge">{plan.badge}</span>}
                  </div>
                  <p className="pricing-price">
                    {formatNtd(plan.monthly_price_ntd)}<small>／月</small>
                  </p>
                  <p className="pricing-coins">每月 {formatCoins(plan.monthly_coins)}</p>
                  {plan.features?.length > 0 && (
                    <ul className="pricing-features">
                      {plan.features.map((feature) => (
                        <li key={feature}><CheckCircleIcon /> {feature}</li>
                      ))}
                    </ul>
                  )}
                  <NavLink to={checkoutTo} className="public-cta-ghost pricing-plan-cta">{planCta}</NavLink>
                </li>
              ))}
            </ul>
          </>
        )}

        {plans.packs.length > 0 && (
          <>
            <h3 className="pricing-group-title">點數包（一次付清）</h3>
            <ul className="pricing-plans">
              {plans.packs.map((plan) => (
                <li key={plan.code} className="pub-card pricing-plan">
                  <div className="pricing-plan-head">
                    <h4>{plan.name}</h4>
                    {plan.badge && <span className="pricing-badge">{plan.badge}</span>}
                  </div>
                  <p className="pricing-price">{formatNtd(plan.price_ntd)}</p>
                  <p className="pricing-coins">{formatCoins(plan.coin_amount)}</p>
                  {plan.description && <p className="pricing-desc">{plan.description}</p>}
                  <NavLink to={checkoutTo} className="public-cta-ghost pricing-plan-cta">{planCta}</NavLink>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section className="public-section">
        <header className="public-section-head">
          <h2>為什麼選 Argus</h2>
          <p>Argus、自己整合工具、市面上的健檢工具，三者比一比。</p>
        </header>
        <div className="public-compare-wrap">
          <table className="public-compare-table">
            <thead>
              <tr>
                <th className="public-compare-feature">功能</th>
                <th className="public-compare-argus">
                  <div className="public-compare-brand">ARGUS</div>
                </th>
                <th>自己整合</th>
                <th>一般健檢工具</th>
              </tr>
            </thead>
            <tbody>
              {COMPARE_ROWS.map((row) => (
                <tr key={row.feature}>
                  <td className="public-compare-feature">{row.feature}</td>
                  <td className="public-compare-argus">
                    <CheckCircleIcon className="pricing-check" />
                    <span className="pub-sr-only">有</span>
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
          {PURCHASE_FAQ.map((item) => (
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
            <h2 className="public-final-cta-title">先免費完整掃一次</h2>
            <p className="public-final-cta-sub">第一次完整掃描不扣點，看完報告再決定要不要買點數或訂閱。</p>
          </div>
          <NavLink
            to={accessToken ? "/projects" : "/login?tab=register"}
            className="public-cta-primary public-final-cta-btn"
          >
            {accessToken ? "開始掃描 →" : "免費註冊 →"}
          </NavLink>
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

// 快速檢查分頁：圖示沿用首頁的線條圖示（.hx-icon-box），不用 emoji
const FREE_TOOL_TABS = [
  { key: "scan", label: "單頁檢查", Icon: ScoreIcon },
  { key: "speed", label: "網站測速", Icon: GaugeIcon },
  { key: "phish", label: "釣魚偵測", Icon: ShieldIcon },
];

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

      <div className="insight-tabs" role="group" aria-label="選擇檢查工具">
        {FREE_TOOL_TABS.map(({ key, label, Icon }) => (
          <button
            key={key}
            type="button"
            className={`insight-tab ${tool === key ? "active" : ""}`}
            aria-pressed={tool === key}
            onClick={() => setTool(key)}
          >
            <span className="hx-icon-box insight-tab-icon"><Icon /></span>
            {label}
          </button>
        ))}
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


// 下載頁（/download，2026-10-10 改版）：圖示改用全站線條圖示，不用 emoji。
// 安裝卡片的圖示＝該平台要按的關鍵按鈕（安裝圖示／⋮ 選單／分享），平台名稱寫在標題。
// 離線說明依 public/service-worker.js 的實際行為：只快取介面資源，API 不寫入快取。
const INSTALL_BENEFITS = [
  {
    Icon: MonitorIcon,
    title: "像 App 一樣開啟",
    desc: "從桌面或主畫面一鍵進入，以獨立視窗執行，不用每次找分頁或輸入網址。",
  },
  {
    Icon: SparkIcon,
    title: "自動保持最新版",
    desc: "不經過 App Store，Argus 更新後下次開啟就是新版本，不需要手動下載安裝檔。",
  },
  {
    Icon: ClockIcon,
    title: "開啟更快",
    desc: "介面資源會保存在裝置上，再次開啟更快；掃描結果與報告仍需要連線才能讀取。",
  },
];

const INSTALL_PLATFORMS = [
  {
    Icon: DownloadIcon,
    platform: "電腦（Chrome／Edge）",
    key: "網址列右側的安裝圖示",
    steps: ["點網址列右側的「安裝」圖示（或瀏覽器選單裡的「安裝 Argus」）", "按「安裝」，桌面與開始選單就會出現 Argus"],
  },
  {
    Icon: MoreIcon,
    platform: "Android（Chrome）",
    key: "右上角 ⋮ 選單",
    steps: ["點右上角的 ⋮ 選單", "選「加到主畫面」或「安裝應用程式」並確認"],
  },
  {
    Icon: ShareIcon,
    platform: "iPhone／iPad（Safari）",
    key: "下方的分享按鈕",
    steps: ["用 Safari 開啟本網站，點下方的分享按鈕", "選「加入主畫面」，再按右上角「新增」"],
  },
];

function formatReleaseDate(value) {
  return value ? new Date(value).toLocaleDateString("zh-Hant") : "";
}

function DownloadPage() {
  const [releases, setReleases] = useState([]);
  const { canInstall, installed, trigger } = useInstallPrompt();
  useEffect(() => {
    api.get("/content/releases/").then((r) => setReleases(r.data.releases || [])).catch(() => {});
  }, []);
  const latest = releases.find((r) => r.is_latest) || releases[0];
  return (
    <div className="public-page download-page">
      <section className="public-hero compact">
        <div className="public-hero-bg" aria-hidden="true">
          <span className="hero-orb hero-orb-1" />
          <span className="hero-orb hero-orb-2" />
        </div>
        <div className="public-hero-content">
          <span className="public-hero-eyebrow">DOWNLOAD · 安裝 App</span>
          <h1 className="public-hero-title">
            <span className="hero-grad">一鍵安裝</span> Argus
          </h1>
          <p className="public-hero-sub">
            Argus 是漸進式網頁應用（PWA），不需要經過 App Store：從瀏覽器加入桌面或主畫面，就能像 App 一樣開啟。
          </p>
          <div className="public-hero-actions">
            {installed ? (
              <span className="public-install-installed">
                <CheckCircleIcon className="install-inline-icon" /> 已安裝，請從桌面或主畫面開啟
              </span>
            ) : (
              <button
                type="button"
                className="public-cta-primary install-cta"
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
                <DownloadIcon className="install-inline-icon" /> 安裝 Argus
              </button>
            )}
            {!installed && latest?.download_url && (
              <a className="public-cta-ghost" href={latest.download_url}>
                取得 {latest.platform_label} 版 →
              </a>
            )}
          </div>
          {!installed && !canInstall && (
            <p className="install-hero-hint">這個瀏覽器不支援一鍵安裝時，按鈕會帶你到下方的手動步驟。</p>
          )}
        </div>
      </section>

      <section className="public-section">
        <header className="public-section-head">
          <h2>安裝後可以做什麼</h2>
          <p>功能與網頁版完全相同，只是開啟更方便。</p>
        </header>
        <ul className="pub-card-grid">
          {INSTALL_BENEFITS.map(({ Icon, title, desc }) => (
            <li key={title} className="pub-card">
              <span className="hx-icon-box"><Icon /></span>
              <h3>{title}</h3>
              <p>{desc}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="public-section" id="install-guide">
        <header className="public-section-head">
          <h2>安裝步驟</h2>
          <p>找到各平台的關鍵按鈕，兩步完成。</p>
        </header>
        <ul className="pub-card-grid">
          {INSTALL_PLATFORMS.map(({ Icon, platform, key, steps }) => (
            <li key={platform} className="pub-card install-platform">
              <div className="install-platform-head">
                <span className="hx-icon-box"><Icon /></span>
                <div>
                  <h3>{platform}</h3>
                  <p className="install-platform-key">關鍵按鈕：{key}</p>
                </div>
              </div>
              <ol className="install-steps">
                {steps.map((step) => <li key={step}>{step}</li>)}
              </ol>
            </li>
          ))}
        </ul>
      </section>

      {latest && (
        <section className="public-section">
          <header className="public-section-head">
            <h2>版本資訊</h2>
            <p>最新版 {latest.version}（{latest.platform_label}）</p>
          </header>
          <div className="pub-card install-release">
            <div className="install-release-head">
              <span className="pricing-badge">最新</span>
              <strong>v{latest.version}</strong>
              <span className="install-release-date">{formatReleaseDate(latest.released_at)}</span>
            </div>
            {latest.release_notes && <p className="install-release-notes">{latest.release_notes}</p>}
            {latest.download_url && (
              <a className="public-cta-ghost" href={latest.download_url}>
                <DownloadIcon className="install-inline-icon" /> 取得 {latest.platform_label}
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
                    <span className="public-release-history-date">{formatReleaseDate(r.released_at)}</span>
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
