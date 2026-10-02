import { useCallback, useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate, useParams } from "react-router-dom";

import { api } from "../../api";
import { useArgusStore } from "../../store";
import brandLogo from "../../assets/brand-logo.webp";
import argusEyeStill from "../../assets/argus-eye-still.webp";
import argusEye from "../../assets/argus-eye.webp";
import { ScanPipeline } from "../../components/public/ScanPipeline.jsx";
import {
  ChartIcon,
  CoinIcon,
  DocIcon,
  EyeIcon,
  FlagIcon,
  GlobeIcon,
  LockIcon,
  MagnifierIcon,
  RobotIcon,
  ShieldIcon,
  SpiderIcon,
} from "../../shared/LineIcons.jsx";
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
    ],
  },
];

function PublicFooter() {
  return (
    <footer className="public-footer">
      <div className="public-footer-inner">
        <div className="public-footer-about">
          <img src={brandLogo} className="public-footer-logo" alt="ARGUS" width="96" height="64" />
          <div className="public-footer-sub">授權式 AI 網站健檢平台</div>
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
          © Argus · 僅供授權測試的網站健檢工具
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


// 首頁的產品預覽視窗：模擬一次掃描進行中的畫面。
//
// 這是示意畫面不是真實掃描，所以標題列標了「示意」——首頁放一個看起來像
// 真實資料的東西卻不說明，等於誤導。
//
// 四筆 finding 對應真實規則：HTTPS（security）、JSON-LD（geo）、
// alt 屬性（seo）、llms.txt（geo/AEO），嚴重度也照實際的評分權重排。
const DEMO_FINDINGS = [
  { sev: "high", tag: "HIGH", cat: "SECURITY", title: "頁面未使用 HTTPS", meta: "影響 3 個頁面" },
  { sev: "medium", tag: "MED", cat: "GEO", title: "缺少 JSON-LD 結構化資料", meta: "AI 無法辨識實體" },
  { sev: "low", tag: "LOW", cat: "SEO", title: "圖片缺 alt 屬性", meta: "3 張圖片" },
  { sev: "info", tag: "INFO", cat: "AEO", title: "建議加 llms.txt 給 AI 爬蟲", meta: "尚未建立" },
];

function ProjectScanDemo() {
  return (
    <div className="demo-win">
      <div className="demo-bar">
        <span className="demo-dot demo-dot-r" />
        <span className="demo-dot demo-dot-y" />
        <span className="demo-dot demo-dot-g" />
        <span className="demo-url">
          <LockIcon className="demo-url-icon" />
          argus.example.com
        </span>
        <span className="demo-tag">示意</span>
      </div>

      <div className="demo-body">
        <div className="demo-phase">
          <span className="demo-phase-icon"><SpiderIcon /></span>
          <span className="demo-phase-text">
            <strong>爬取中</strong>
            <span className="demo-phase-sub">12 / 50 頁 · 已用 00:42</span>
          </span>
          <span className="demo-live">
            <span className="demo-live-dot" />
            即時
          </span>
        </div>

        <div className="demo-progress" role="presentation">
          <span className="demo-progress-fill" />
        </div>

        <ul className="demo-findings">
          {DEMO_FINDINGS.map((f, i) => (
            <li
              className={`demo-finding sev-${f.sev}`}
              key={f.title}
              style={{ animationDelay: `${0.5 + i * 0.45}s` }}
            >
              <span className="demo-sev">{f.tag}</span>
              <span className="demo-finding-main">
                <span className="demo-finding-title">{f.title}</span>
                <span className="demo-finding-meta">{f.meta}</span>
              </span>
              <span className="demo-cat">{f.cat}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

const PROJECT_FEATURES_FALLBACK = [
  { id: -1, icon: "🕷️", title: "BFS 深度爬蟲", description: "以 Playwright 驅動的 BFS 爬蟲，自動探索整站結構。" },
  { id: -2, icon: "🔍", title: "四維安全掃描", description: "涵蓋 SEO、AEO、GEO、Security 四個維度的全面分析。" },
  { id: -3, icon: "🤖", title: "Hermes AI Agent", description: "LLM 驅動的智慧代理人，提供主動式漏洞驗證。" },
  { id: -4, icon: "📊", title: "即時進度追蹤", description: "掃描進度即時更新，支援多任務並行管理。" },
  { id: -5, icon: "📝", title: "Word 報告匯出", description: "一鍵產生專業 Word 格式掃描報告，方便交付客戶。" },
  { id: -6, icon: "💎", title: "點數計費系統", description: "靈活的 Coin 計費模式，按頁計費，精準控制成本。" },
];

// 核心功能的內容來自 CMS（/content/features/），管理員在後台填的是 emoji。
// 首頁改用描邊圖示後，這張表把 emoji 對映到對應圖示；沒對到的用放大鏡當預設。
// 不直接改 CMS 欄位型別，是為了不動到後台既有的編輯流程。
const FEATURE_ICON_BY_EMOJI = {
  "🕷️": SpiderIcon, "🕷": SpiderIcon,
  "🔍": MagnifierIcon, "🔎": MagnifierIcon,
  "🤖": RobotIcon,
  "📊": ChartIcon, "📈": ChartIcon,
  "📝": DocIcon, "📄": DocIcon, "📃": DocIcon,
  "💎": CoinIcon, "💰": CoinIcon, "🪙": CoinIcon,
  "🔐": LockIcon, "🔒": LockIcon,
  "🛡️": ShieldIcon, "🛡": ShieldIcon,
  "🌐": GlobeIcon,
  "👀": EyeIcon, "👁": EyeIcon,
  "🚀": FlagIcon, "🎯": FlagIcon,
};

// 安全邊界：每一項都對應實際程式，不是文宣口號
const PROJECT_SAFETY = [
  {
    key: "consent", tone: "cyan", Icon: LockIcon, title: "授權確認",
    desc: "每次任務記錄 IP、時間、User-Agent 與授權勾選狀態；第三方或敏感網域要求二次確認。",
  },
  {
    key: "same-origin", tone: "teal", Icon: GlobeIcon, title: "同網域邏輯",
    desc: "爬蟲與 finding 證據只限授權目標的同網域頁面，不會跨域追蹤或污染他站。",
  },
  {
    key: "ssrf", tone: "violet", Icon: ShieldIcon, title: "SSRF 應用層防護",
    desc: "入口、轉址、子資源與 WebSocket 均檢查公開位址；正式環境仍須搭配出站網路政策。",
  },
  {
    key: "passive", tone: "amber", Icon: EyeIcon, title: "預設被動模式",
    desc: "預設不做破壞性或主動式漏洞攻擊；主動模式需額外勾選、通過網域驗證且記入稽核軌跡。",
  },
];

// ── 首頁內容（皆以現有程式碼核對過，不宣稱尚未實作的能力）──

// 檢測涵蓋的面向：檢查項目對應 backend/apps/scans/scanners.py 與 security/ 的實際規則。
const PROJECT_COVERAGE = [
  {
    key: "seo",
    code: "SEO",
    name: "搜尋可見度",
    checks: "Meta title／description 長度、H1 數量、圖片 alt、canonical、Open Graph 標籤",
  },
  {
    key: "aeo",
    code: "AEO",
    name: "答案引擎",
    checks: "問答內容是否有 FAQPage／HowTo 結構化資料、問答段落是否結構清楚",
  },
  {
    key: "geo",
    code: "GEO",
    name: "生成式搜尋",
    checks: "JSON-LD 實體類型、語意化主內容區塊、可引用段落、llms.txt、robots.txt 是否擋掉 AI 爬蟲",
  },
  {
    key: "security",
    code: "資安",
    name: "被動資安",
    checks: "HTTPS 與憑證、CSP／HSTS 等安全標頭、Cookie 旗標、SPF／DMARC、敏感檔案外洩、含已知漏洞的前端函式庫",
  },
  {
    key: "ux",
    code: "UX",
    name: "使用體驗",
    checks: "以行動版視窗實際渲染，檢查是否出現水平捲動破版",
  },
];

const PROJECT_METHODS = [
  { title: "真實瀏覽器渲染", desc: "以 Playwright 開啟每一頁，檢查的是使用者實際看到的 DOM，並逐頁截圖。" },
  { title: "同網域爬取", desc: "從入口網址依 BFS 探索同網域頁面，範圍與頁數在建立掃描時決定。" },
  { title: "被動為預設", desc: "預設只讀取公開回應；主動式資安工具必須先完成網域所有權驗證才會啟用。" },
];

// 使用者會拿到什麼：對應 ScanDetailPage、reports.py（Word）、fixgen、/verify。
const PROJECT_DELIVERABLES = [
  {
    no: "01",
    title: "互動式報告",
    desc: "逐頁截圖上直接框出問題位置，可依嚴重度與維度篩選，並列出最該先處理的幾件事。",
  },
  {
    no: "02",
    title: "Word 報告",
    desc: "一鍵匯出 .docx，附唯一報告編號；收件者可在「報告查驗」頁以 SHA-256 指紋核對內容未被竄改。",
  },
  {
    no: "03",
    title: "修正產出",
    desc: "依掃描結果產生 JSON-LD、Open Graph／meta、llms.txt 與 FAQ Schema，可直接複製貼上；需人工確認的欄位會明確標示。",
  },
  {
    no: "04",
    title: "網站拓樸",
    desc: "以圖呈現爬到的頁面與連結關係，孤立頁與被阻擋的頁面一眼看出。",
  },
];

// 每一筆 finding 帶的證據欄位（Finding model：evidence / bounding_box / rule_id / remediation / ai_explanation）。
const PROJECT_EVIDENCE = [
  { label: "位置", desc: "問題所在的頁面網址，與截圖上的框選座標；站台層級的問題另外標示。" },
  { label: "證據", desc: "觸發規則的原始片段，例如 HTML 標籤、回應標頭或 DNS 紀錄。" },
  { label: "規則與嚴重度", desc: "規則代號、嚴重度與優先分數，排序有依據而不是主觀判斷。" },
  { label: "修正方向", desc: "每一筆都附修正建議；AI 補充說明會標註使用的模型，方便判斷可信度。" },
];

const HOME_FAQ = [
  {
    q: "快速檢查和完整掃描差在哪？",
    a: "快速檢查免登入、不扣點，只分析單一頁面的 HTML 與回應標頭；完整掃描會以真實瀏覽器爬取整站、逐頁截圖，並產出互動報告與可直接貼上的修正內容。",
  },
  {
    q: "完整掃描怎麼計費？",
    a: "按維度計費：每頁每維度 2 coin，只勾需要的維度就好。建立時依最大頁數預扣，完成後依實際頁數退回；掃描失敗或被取消會全額退回。登入後每月自動贈 200 coin。",
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

// 核心功能卡數量來自 CMS、不固定：挑讓最後一列最滿的欄數，避免「5 張＋孤零零 1 張」。
function featureColumns(count) {
  if (count <= 4) return Math.max(count, 1);
  const exact = [4, 3].find((c) => count % c === 0);
  if (exact) return exact;
  return [4, 3].reduce((best, c) => (count % c > count % best ? c : best), 4);
}

function ProjectPage() {
  const [features, setFeatures] = useState(PROJECT_FEATURES_FALLBACK);
  useEffect(() => {
    api.get("/content/features/")
      .then((r) => {
        const list = r.data.features || [];
        if (list.length) setFeatures(list);
      })
      .catch(() => {});
  }, []);
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

      {/* 產品預覽緊接 hero：先讓訪客看到東西長什麼樣 */}
      <section className="public-section public-section-demo">
        <ProjectScanDemo />
      </section>

      {/* 檢測涵蓋的面向與方法：用列表與分隔線呈現，不再每項一張卡 */}
      <section className="public-section home-coverage" aria-labelledby="home-coverage-title">
        <header className="public-section-head">
          <h2 id="home-coverage-title">檢測涵蓋的面向與方法</h2>
          <p>一次掃描同時檢查五個面向，每個問題都標明屬於哪一個</p>
        </header>
        <dl className="home-coverage-list">
          {PROJECT_COVERAGE.map((item) => (
            <div className="home-coverage-row" data-cat={item.key} key={item.key}>
              <dt>
                <span className="home-coverage-code">{item.code}</span>
                <span className="home-coverage-name">{item.name}</span>
              </dt>
              <dd>{item.checks}</dd>
            </div>
          ))}
        </dl>
        <ul className="home-methods">
          {PROJECT_METHODS.map((m) => (
            <li key={m.title}>
              <h3>{m.title}</h3>
              <p>{m.desc}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="public-section">
        <ScanPipeline />
      </section>

      {/* 使用者會拿到什麼 ＋ 報告如何提供證據 */}
      <section className="public-section home-deliver" aria-labelledby="home-deliver-title">
        <header className="public-section-head">
          <h2 id="home-deliver-title">你會拿到什麼</h2>
          <p>不只是一份問題清單，而是能直接交付、直接修正的結果</p>
        </header>
        <ol className="home-deliver-list">
          {PROJECT_DELIVERABLES.map((d) => (
            <li key={d.no}>
              <span className="home-deliver-no">{d.no}</span>
              <h3>{d.title}</h3>
              <p>{d.desc}</p>
            </li>
          ))}
        </ol>

        <div className="home-evidence">
          <div className="home-evidence-copy">
            <h3>每個問題都附證據與修正方向</h3>
            <p>
              報告裡的每一筆問題都能追溯到頁面上的實際位置與觸發它的原始內容，
              接手的工程師不需要重新排查，就能判斷要不要修、怎麼修。
            </p>
            <dl className="home-evidence-fields">
              {PROJECT_EVIDENCE.map((e) => (
                <div key={e.label}>
                  <dt>{e.label}</dt>
                  <dd>{e.desc}</dd>
                </div>
              ))}
            </dl>
          </div>
          <figure className="home-evidence-sample" aria-label="報告中一筆問題的示意">
            <figcaption>報告中的一筆問題（示意）</figcaption>
            <div className="home-evidence-head">
              <span className="home-evidence-sev">HIGH</span>
              <span className="home-evidence-cat">SECURITY</span>
              <strong>缺少 Content-Security-Policy 標頭</strong>
            </div>
            <dl className="home-evidence-kv">
              <div><dt>頁面</dt><dd>https://example.com/</dd></div>
              <div><dt>規則</dt><dd>header-csp-missing</dd></div>
              <div><dt>證據</dt><dd>回應標頭中找不到 Content-Security-Policy</dd></div>
              <div><dt>修正</dt><dd>在伺服器回應加入 CSP，先以 Report-Only 觀察後再強制執行</dd></div>
            </dl>
          </figure>
        </div>
      </section>

      <section className="public-section">
        <header className="public-section-head">
          <h2>核心功能</h2>
          <p>從爬取到修正產出，一條龍完成</p>
        </header>
        <div className="public-panel-grid home-feature-grid" data-cols={featureColumns(features.length)}>
          {features.map((f, i) => {
            // CMS 存的是 emoji；對不到就退回放大鏡，不讓畫面缺圖示
            const Icon = FEATURE_ICON_BY_EMOJI[f.icon] || MagnifierIcon;
            const tone = ["cyan", "teal", "violet", "amber"][i % 4];
            return (
              <article className="public-panel" data-tone={tone} key={f.id}>
                <span className="public-panel-icon"><Icon /></span>
                <h3 className="public-panel-title">{f.title}</h3>
                <p className="public-panel-desc">{f.description}</p>
              </article>
            );
          })}
          {features.length === 0 && (
            <p className="public-empty">尚未設定功能介紹。</p>
          )}
        </div>
      </section>

      <section className="public-section">
        <header className="public-section-head">
          <h2>安全邊界</h2>
          <p>每一項都對應實際程式碼，不是文宣</p>
        </header>
        <div className="public-panel-grid">
          {PROJECT_SAFETY.map((item) => (
            <article className="public-panel" data-tone={item.tone} key={item.key}>
              <span className="public-panel-icon"><item.Icon /></span>
              <h3 className="public-panel-title">{item.title}</h3>
              <p className="public-panel-desc">{item.desc}</p>
            </article>
          ))}
        </div>
      </section>

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
            <p className="public-final-cta-sub">想先試用？「快速檢查」免登入、不扣點；登入後每月自動贈 200 coin，掃描依實際頁數計點。</p>
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
    a: "目前串接綠界測試環境（Stage）的信用卡付款：送出訂單後導向綠界付款頁，付款完成由綠界回傳通知後才會入點。尚未開放正式金流。",
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
    feature: "Word 報告自動匯出",
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

const RISK_LABELS = {
  high: "高風險",
  medium: "中風險",
  low: "低風險",
  minimal: "低訊號",
};

function RiskLevelBadge({ level }) {
  return (
    <span className={`insight-risk-badge risk-${level || "minimal"}`}>
      {RISK_LABELS[level] || "未判定"}
    </span>
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
            <strong>免登入、不扣點數、即時出結果。</strong>單頁測速參考 PageSpeed / Lighthouse 的效能思路；
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
          <p>輸入一個網址，立即看 SEO / 資安 / AEO·GEO 的單頁體檢分數與重點問題；完整多頁＋AI 深掃請登入後到「掃描」</p>
        </header>
        <div className="insight-tool-layout">
          <form className="insight-tool-card" onSubmit={runQuickScan}>
            <h3 className="insight-card-title">單頁快速檢查</h3>
            <label className="insight-field">
              <span>網址</span>
              <input
                value={quickForm.url}
                onChange={(e) => setQuickForm((f) => ({ ...f, url: e.target.value }))}
                placeholder="https://example.com/"
                required
              />
            </label>
            <label className="insight-check">
              <input
                type="checkbox"
                checked={quickForm.authorization_confirmed}
                onChange={(e) => setQuickForm((f) => ({ ...f, authorization_confirmed: e.target.checked }))}
              />
              <span>我確認此頁面可公開檢測，或我擁有分析授權。</span>
            </label>
            {quick.error && <div className="insight-error">{quick.error}</div>}
            <button type="submit" className="public-cta-primary" disabled={quick.loading}>
              {quick.loading ? "檢查中..." : "開始單頁檢查"}
            </button>
          </form>

          <div className="insight-result-card">
            {!quick.result ? (
              <div className="insight-empty">
                <strong>會輸出哪些結果</strong>
                <span>整體分數 + SEO / 資安 / AEO·GEO 三維單頁分數與重點問題清單。</span>
              </div>
            ) : (
              <>
                <div className="insight-score-row">
                  <div className={`insight-score score-${quick.result.grade}`}>
                    {quick.result.overall_score}
                  </div>
                  <div>
                    <div className="insight-result-title">{quick.result.final_url}</div>
                    <div className="insight-result-sub">單頁快速檢查（不含多頁爬蟲 / Playwright）</div>
                  </div>
                </div>
                <div className="insight-metrics-grid">
                  {quick.result.categories.map((c) => (
                    <div key={c.key}><span>{c.label}</span><strong>{c.score}</strong></div>
                  ))}
                </div>
                {quick.result.findings.length > 0 ? (
                  <ul className="insight-finding-list">
                    {quick.result.findings.map((f, idx) => (
                      <li key={`${f.title}-${idx}`}>
                        <strong>{f.title}</strong>
                        <span>{f.detail}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="insight-success">單頁檢查未發現明顯問題。</div>
                )}
                <p className="insight-note">{quick.result.note}</p>
                {/* 導流 CTA（修正產出票06）：只講完整掃描的加值與入口，
                    不提供任何免費產生——修正產出對應的是一份付費掃描結果。 */}
                <div className="insight-upsell">
                  <strong>完整掃描可獲得可直接貼上的修正內容</strong>
                  <span>
                    JSON-LD、Open Graph＋meta、llms.txt 與 FAQ Schema，
                    以網站實際內容產生、可直接複製採用；付費掃描附贈 1 次產生額度。
                  </span>
                  <button
                    type="button"
                    className="public-cta-primary"
                    onClick={() => navigate("/login")}
                  >
                    登入建立完整掃描
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </section>
      )}

      {tool === "speed" && (
      <section className="public-section">
        <header className="public-section-head">
          <h2>網站測速分析</h2>
          <p>單一 URL、單次請求，不扣 coin，不啟動全站爬蟲</p>
        </header>
        <div className="insight-tool-layout">
          <form className="insight-tool-card" onSubmit={runSpeedTest}>
            <label className="insight-field">
              <span>網址</span>
              <input
                value={speedForm.url}
                onChange={(e) => setSpeedForm((f) => ({ ...f, url: e.target.value }))}
                placeholder="https://example.com/"
                required
              />
            </label>
            <label className="insight-check">
              <input
                type="checkbox"
                checked={speedForm.authorization_confirmed}
                onChange={(e) => setSpeedForm((f) => ({ ...f, authorization_confirmed: e.target.checked }))}
              />
              <span>我確認此頁面可公開測速，或我擁有分析授權。</span>
            </label>
            {speed.error && <div className="insight-error">{speed.error}</div>}
            <button type="submit" className="public-cta-primary" disabled={speed.loading}>
              {speed.loading ? "測速中..." : "開始測速"}
            </button>
          </form>

          <div className="insight-result-card">
            {!speed.result ? (
              <div className="insight-empty">
                <strong>會輸出哪些結果</strong>
                <span>分數、TTFB、傳輸量、阻塞 script、圖片 lazy loading、快取與壓縮建議。</span>
              </div>
            ) : (
              <>
                <div className="insight-score-row">
                  <div className={`insight-score score-${speed.result.grade}`}>
                    {speed.result.score}
                  </div>
                  <div>
                    <div className="insight-result-title">{speed.result.final_url}</div>
                    <div className="insight-result-sub">{speed.result.source}</div>
                  </div>
                </div>
                <div className="insight-metrics-grid">
                  <div><span>TTFB</span><strong>{speed.result.metrics.ttfb_ms} ms</strong></div>
                  <div><span>傳輸量</span><strong>{speed.result.metrics.transfer_kb} KB</strong></div>
                  <div><span>阻塞 script</span><strong>{speed.result.metrics.blocking_scripts}</strong></div>
                  <div><span>圖片</span><strong>{speed.result.metrics.images}</strong></div>
                </div>
                <p className="insight-note">{speed.result.core_web_vitals_note}</p>
                {speed.result.findings.length > 0 ? (
                  <ul className="insight-finding-list">
                    {speed.result.findings.map((f, idx) => (
                      <li key={`${f.title}-${idx}`}>
                        <strong>{f.title}</strong>
                        <span>{f.description}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="insight-success">未發現明顯效能風險。</div>
                )}
              </>
            )}
          </div>
        </div>
      </section>
      )}

      {tool === "phish" && (
      <section className="public-section">
        <header className="public-section-head">
          <h2>可疑網址 / 詐騙郵件檢測</h2>
          <p>貼上一個網址或一封郵件內容，本機特徵分類器幫你判斷「是否可能是釣魚／詐騙」（不外送大模型 API）</p>
        </header>
        <div className="insight-two-col">
          <form className="insight-tool-card" onSubmit={runUrlCheck}>
            <h3 className="insight-card-title">網址安全檢測（防釣魚）</h3>
            <label className="insight-field">
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
              {urlCheck.loading ? "分析中..." : "分析 URL"}
            </button>
            {urlCheck.result && (
              <div className="insight-risk-result">
                <div className="insight-risk-head">
                  <strong>{urlCheck.result.risk_score}/100</strong>
                  <RiskLevelBadge level={urlCheck.result.risk_level} />
                </div>
                <p>{urlCheck.result.recommendation}</p>
                <ul className="insight-feature-list">
                  {urlCheck.result.features.slice(0, 5).map((f, idx) => (
                    <li key={`${f.title}-${idx}`}>
                      <strong>{f.title}</strong>
                      <span>{f.evidence}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </form>

          <form className="insight-tool-card" onSubmit={runEmailCheck}>
            <h3 className="insight-card-title">郵件詐騙檢測（防釣魚信）</h3>
            <label className="insight-field">
              <span>.eml / 原始信件內容</span>
              <textarea
                value={emailValue}
                onChange={(e) => setEmailValue(e.target.value)}
                placeholder={"From: notice@example.com\nAuthentication-Results: ...\n\n請立即驗證帳號..."}
                rows={9}
                required
              />
            </label>
            {emailCheck.error && <div className="insight-error">{emailCheck.error}</div>}
            <button type="submit" className="public-cta-primary" disabled={emailCheck.loading}>
              {emailCheck.loading ? "分析中..." : "分析郵件"}
            </button>
            {emailCheck.result && (
              <div className="insight-risk-result">
                <div className="insight-risk-head">
                  <strong>{emailCheck.result.risk_score}/100</strong>
                  <RiskLevelBadge level={emailCheck.result.risk_level} />
                </div>
                <p>{emailCheck.result.recommendation}</p>
                <div className="insight-email-meta">
                  <span>From: {emailCheck.result.from_domain || "未解析"}</span>
                  <span>連結數: {emailCheck.result.url_count}</span>
                </div>
                <ul className="insight-feature-list">
                  {emailCheck.result.features.slice(0, 5).map((f, idx) => (
                    <li key={`${f.title}-${idx}`}>
                      <strong>{f.title}</strong>
                      <span>{f.evidence}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </form>
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
  // 讀者可能是「收到 .docx 的第三方」而不是 Argus 使用者：網址帶編號就直接查，
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
                  可自行計算該 .docx 的 SHA-256 並與下方指紋比對。
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
