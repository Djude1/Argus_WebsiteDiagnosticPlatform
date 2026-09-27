import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";

import { api } from "../../api";
import argusEyeStill from "../../assets/argus-eye-still.webp";
import argusEye from "../../assets/argus-eye.webp";
import { IrisScore } from "../../components/brand/IrisScore";
import { DimensionGrid } from "../../components/public/DimensionGrid";
import { HeroQuickCheck } from "../../components/public/HeroQuickCheck";
import { PublicSection } from "../../components/public/PublicHero";
import { PublicFaq } from "../../components/public/PublicFaq";
import { ScanDemoWindow } from "../../components/public/ScanDemoWindow";
import { ScanPipeline } from "../../components/public/ScanPipeline";
import TechMarquee from "../../components/public/TechMarquee";
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
} from "../../shared/LineIcons";
import { formatDate } from "../../shared/formatters";
import { PROJECT_PLATFORM_STATS } from "./platformStats";

const PROJECT_STACK_POINTS = [
  "前端 React 18 + Vite，後端 Django 5 + DRF",
  "Celery + Redis 排程，Playwright 驅動真實瀏覽器",
  "Docker 容器化，Argo CD 部署到 Kubernetes",
];

const PROJECT_FEATURES_FALLBACK = [
  { id: -1, icon: "🕷️", title: "BFS 深度爬蟲", description: "以 Playwright 驅動的 BFS 爬蟲，自動探索整站結構。" },
  { id: -2, icon: "🔍", title: "多維度掃描", description: "涵蓋 SEO、AEO、GEO、資安與 UX 的全面分析。" },
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

// 功能卡數量來自 CMS、不固定。挑一個讓最後一列最滿的欄數（4 → 3 → 2），
// 最後一列置中，避免「5 張＋孤零零 1 張」這種排版。
function featureColumns(count) {
  if (count <= 4) return Math.max(count, 1);
  const candidates = [4, 3];
  const exact = candidates.find((c) => count % c === 0);
  if (exact) return exact;
  return candidates.reduce((best, c) => (count % c > count % best ? c : best), candidates[0]);
}

// 安全邊界：每一項都對應實際程式，不是文宣口號
const PROJECT_SAFETY = [
  {
    key: "consent", Icon: LockIcon, title: "授權確認",
    desc: "每次任務記錄 IP、時間、User-Agent 與授權勾選狀態；第三方或敏感網域要求二次確認。",
  },
  {
    key: "same-origin", Icon: GlobeIcon, title: "同網域邏輯",
    desc: "爬蟲與 finding 證據只限授權目標的同網域頁面，不會跨域追蹤或污染他站。",
  },
  {
    key: "ssrf", Icon: ShieldIcon, title: "SSRF 應用層防護",
    desc: "入口、轉址、子資源與 WebSocket 均檢查公開位址；正式環境仍須搭配出站網路政策。",
  },
  {
    key: "passive", Icon: EyeIcon, title: "預設被動模式",
    desc: "預設不做破壞性或主動式漏洞攻擊；主動模式需額外勾選、通過網域驗證且記入稽核軌跡。",
  },
];

// 首頁 FAQ：只回答站上其他地方已經寫明的事實（計費、授權、查驗），不另外承諾
const HOME_FAQ = [
  {
    q: "快速檢查和完整掃描差在哪？",
    a: "快速檢查免登入、不扣點，只分析單一頁面的 HTML 與回應標頭；完整掃描會以真實瀏覽器爬取整站、逐頁截圖，並產出可互動報告與可直接貼上的修正內容。",
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

function HomeHero() {
  return (
    <section className="home-hero">
      <div className="home-hero-backdrop ag-surface-grid" aria-hidden="true" />
      <div className="home-hero-inner">
        <div className="home-hero-copy">
          <span className="ag-eyebrow">AI Website Audit · 百眼守望</span>
          <h1 className="home-hero-title">
            一鍵看見<br />
            <em>網站的所有問題</em>
          </h1>
          <p className="home-hero-sub">
            輸入網址，找出網站在 <strong>SEO、AEO、GEO、資安與 UX</strong> 上的問題，並排好該先處理哪一個——
            修正要用的檔案，直接生給你。
          </p>
          <HeroQuickCheck />
          <NavLink to="/login" className="home-hero-login">
            需要整站多頁掃描？登入建立完整掃描 <span aria-hidden="true">→</span>
          </NavLink>
        </div>

        <div className="home-hero-art" aria-hidden="true">
          <div className="home-hero-scope ag-viewfinder">
            <span className="home-hero-halo" />
            <span className="home-hero-ring" />
            <picture className="home-hero-eye">
              {/* 偏好減少動態者自動換靜態首幀，且不下載動態版 */}
              <source media="(prefers-reduced-motion: reduce)" srcSet={argusEyeStill} />
              <img src={argusEye} alt="" width="256" height="202" />
            </picture>
            <span className="home-hero-sweep" />
            <span className="home-hero-coord tl">LAT 25.04 · WATCH</span>
            <span className="home-hero-coord br">IRIS 12 / 12</span>
          </div>
          <div className="home-hero-card home-hero-card--score">
            <IrisScore score={72} size={64} />
            <span className="home-hero-card-text">
              <strong>範例報告</strong>
              <span>找到 3 個高風險問題，這是修法</span>
            </span>
          </div>
          <div className="home-hero-card home-hero-card--live">
            <span className="home-hero-live-dot" />
            <span className="ag-num">12 / 50 頁</span>
            <span className="home-hero-card-muted">爬取中</span>
          </div>
        </div>
      </div>
    </section>
  );
}

export function ProjectPage() {
  const [features, setFeatures] = useState(PROJECT_FEATURES_FALLBACK);
  const [milestones, setMilestones] = useState([]);
  useEffect(() => {
    api.get("/content/features/")
      .then((r) => {
        const list = r.data.features || [];
        if (list.length) setFeatures(list);
      })
      .catch(() => {});
    api.get("/content/milestones/").then((r) => setMilestones(r.data.milestones || [])).catch(() => {});
  }, []);

  return (
    <div className="public-page home-page">
      <HomeHero />

      <PublicSection
        eyebrow="Five dimensions"
        title="五個維度，一次看完"
        description="同一次掃描同時檢查五個面向，報告裡每個問題都標明屬於哪一維。"
      >
        <DimensionGrid />
      </PublicSection>

      {/* 產品預覽：先讓訪客看到東西長什麼樣，再談流程與安全邊界 */}
      <PublicSection
        className="home-demo-section"
        eyebrow="Live preview"
        title="掃描中與報告，長這樣"
        description="問題依嚴重度排序、標明維度，右側直接給分數與第一個該做的修正。"
      >
        <ScanDemoWindow />
      </PublicSection>

      <section className="public-section">
        <ScanPipeline />
      </section>

      <PublicSection
        eyebrow="Features"
        title="核心功能"
        description="從爬取到修正產出，一條龍完成。"
      >
        {features.length > 0 ? (
          <ul className="feature-grid" data-cols={featureColumns(features.length)}>
            {features.map((f) => {
              // CMS 存的是 emoji；對不到就退回放大鏡，不讓畫面缺圖示
              const Icon = FEATURE_ICON_BY_EMOJI[f.icon] || MagnifierIcon;
              return (
                <li className="feature-card" key={f.id}>
                  <span className="feature-card-icon"><Icon /></span>
                  <span className="feature-card-body">
                    <h3 className="feature-card-title">{f.title}</h3>
                    <p className="feature-card-desc">{f.description}</p>
                  </span>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="public-empty">尚未設定功能介紹。</p>
        )}
      </PublicSection>

      <PublicSection
        eyebrow="Guardrails"
        title="安全邊界"
        description="每一項都對應實際程式碼，不是文宣。"
      >
        <ul className="safety-grid">
          {PROJECT_SAFETY.map((item) => (
            <li className="safety-item" key={item.key}>
              <span className="safety-icon"><item.Icon /></span>
              <span>
                <h3 className="safety-title">{item.title}</h3>
                <p className="safety-desc">{item.desc}</p>
              </span>
            </li>
          ))}
        </ul>
      </PublicSection>

      <PublicSection
        className="home-stats-section"
        eyebrow="By the numbers"
        title="平台規模"
        description="這些數字都能在原始碼裡數出來。"
      >
        <dl className="stat-grid">
          {PROJECT_PLATFORM_STATS.map((s) => (
            <div key={s.label} className="stat-card">
              <dt className="stat-card-label">{s.label}</dt>
              <dd className="stat-card-value ag-num">{s.value}</dd>
              <dd className="stat-card-hint">{s.hint}</dd>
            </div>
          ))}
        </dl>
      </PublicSection>

      {milestones.length > 0 && (
        <PublicSection
          eyebrow="Milestones"
          title="開發歷程"
          description="從 MVP 到上線的關鍵里程碑。"
        >
          <ol className="home-timeline">
            {milestones.map((m, idx) => (
              <li key={m.id} className={`home-timeline-item ${idx === milestones.length - 1 ? "is-latest" : ""}`}>
                <span className="home-timeline-marker" aria-hidden="true"><FlagIcon /></span>
                <div className="home-timeline-body">
                  <time className="home-timeline-date" dateTime={m.date}>{formatDate(m.date)}</time>
                  <h3 className="home-timeline-title">{m.title}</h3>
                  {m.description && <p className="home-timeline-desc">{m.description}</p>}
                </div>
              </li>
            ))}
          </ol>
        </PublicSection>
      )}

      <section className="public-section project-stack">
        <div className="project-stack-intro">
          <span className="ag-eyebrow">Tech stack</span>
          <h2 className="project-stack-title">全棧現代化選型</h2>
          <ul className="project-stack-points">
            {PROJECT_STACK_POINTS.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
        </div>
        <TechMarquee />
      </section>

      <PublicSection eyebrow="FAQ" title="常見問題" className="home-faq-section">
        <PublicFaq items={HOME_FAQ} />
      </PublicSection>

      <section className="public-section">
        <div className="final-cta ag-viewfinder">
          <div className="final-cta-copy">
            <span className="final-cta-eyebrow">準備好了嗎</span>
            <h2 className="final-cta-title">現在就看看，你的網站被看見了多少</h2>
            <p className="final-cta-sub">快速檢查免登入、不扣點；登入後每月自動贈 200 coin，掃描依實際頁數計點。</p>
          </div>
          <div className="final-cta-actions">
            <NavLink to="/free-tools" className="public-cta public-cta-primary">免費快速檢查</NavLink>
            <NavLink to="/purchase" className="public-cta public-cta-ghost">查看方案 →</NavLink>
          </div>
        </div>
      </section>
    </div>
  );
}

export default ProjectPage;
