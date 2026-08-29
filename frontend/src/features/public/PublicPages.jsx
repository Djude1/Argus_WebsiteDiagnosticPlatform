import { useEffect, useMemo, useRef, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { api } from "../../api";
import brandLogo from "../../assets/brand-logo.webp";
import { apiErrorMessage, useInstallPrompt } from "../../shared/AppShared.jsx";
import TechMarquee from "../../components/public/TechMarquee.jsx";
import PublicTopBar from "../../components/navigation/PublicTopBar.jsx";

function PublicFooter() {
  return (
    <footer className="public-footer">
      <div className="public-footer-inner">
        <div>
          <div className="public-footer-brand">⟡ ARGUS</div>
          <div className="public-footer-sub">授權式 AI 網站健檢平台</div>
        </div>
        <div className="public-footer-links">
          <NavLink to="/project">專案介紹</NavLink>
          <NavLink to="/team">團隊</NavLink>
          <NavLink to="/purchase">購買</NavLink>
          <NavLink to="/download">下載 PWA</NavLink>
          <NavLink to="/reviews">評論</NavLink>
        </div>
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
      <PublicTopBar />
      <main className="public-main">
        <Outlet />
      </main>
      <PublicFooter />
    </div>
  );
}

const PROJECT_STACK_POINTS = [
  "前端 React 18 + Vite，後端 Django 5 + DRF",
  "Celery + Redis 排程，Playwright 驅動真實瀏覽器",
  "Docker 容器化，Argo CD 部署到 Kubernetes",
];

const PROJECT_PLATFORM_STATS = [
  { label: "Django Apps", value: "8", hint: "accounts / scans / agent / billing / reviews / admin_api / content / insights" },
  { label: "資料模型", value: "20+", hint: "ScanJob、Finding、CoinWallet、PurchaseOrder…" },
  { label: "自動化測試", value: "250+", hint: "API / 權限 / billing 流程 / 圖片上傳" },
  { label: "REST 端點", value: "40+", hint: "billing / reviews / content / admin / scans / insights" },
];

function ProjectScanDemo() {
  return (
    <div className="project-demo">
      <div className="project-demo-window">
        <div className="project-demo-title-bar">
          <span className="project-demo-dot project-demo-dot-r" />
          <span className="project-demo-dot project-demo-dot-y" />
          <span className="project-demo-dot project-demo-dot-g" />
          <span className="project-demo-url">argus.example.com / 掃描中…</span>
        </div>
        <div className="project-demo-body">
          <div className="project-demo-phase">
            <span className="project-demo-phase-icon">🕷️</span>
            <span>爬蟲中… 12 / 50 頁</span>
            <span className="project-demo-progress">
              <span className="project-demo-progress-fill" />
            </span>
          </div>
          <ul className="project-demo-findings">
            <li className="project-demo-finding sev-high">
              <span className="project-demo-finding-sev">HIGH</span>
              <span className="project-demo-finding-title">頁面未使用 HTTPS</span>
            </li>
            <li className="project-demo-finding sev-medium">
              <span className="project-demo-finding-sev">MED</span>
              <span className="project-demo-finding-title">缺少 JSON-LD 結構化資料</span>
            </li>
            <li className="project-demo-finding sev-low">
              <span className="project-demo-finding-sev">LOW</span>
              <span className="project-demo-finding-title">圖片缺 alt 屬性 ×3</span>
            </li>
            <li className="project-demo-finding sev-info">
              <span className="project-demo-finding-sev">INFO</span>
              <span className="project-demo-finding-title">建議加 llms.txt 給 AI 爬蟲</span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}

// 後台 CMS 可編輯前，先用這份 fallback；API 拉到資料就會覆蓋掉
const PROJECT_FEATURES_FALLBACK = [
  { id: -1, icon: "🕷️", title: "BFS 深度爬蟲", description: "以 Playwright 驅動的 BFS 爬蟲，自動探索整站結構。" },
  { id: -2, icon: "🔍", title: "四維安全掃描", description: "涵蓋 SEO、AEO、GEO、Security 四個維度的全面分析。" },
  { id: -3, icon: "🤖", title: "Hermes AI Agent", description: "LLM 驅動的智慧代理人，提供主動式漏洞驗證。" },
  { id: -4, icon: "📊", title: "即時進度追蹤", description: "掃描進度即時更新，支援多任務並行管理。" },
  { id: -5, icon: "📝", title: "Word 報告匯出", description: "一鍵產生專業 Word 格式掃描報告，方便交付客戶。" },
  { id: -6, icon: "💎", title: "點數計費系統", description: "靈活的 Coin 計費模式，按頁計費，精準控制成本。" },
];

function ProjectPage() {
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
          <img src={brandLogo} className="public-hero-logo" alt="ARGUS" />
          <span className="public-hero-eyebrow">掃描 · 洞察 · 證據</span>
          <h1 className="public-hero-title">
            一鍵看見<span className="hero-grad">網站的所有問題</span>
          </h1>
          <p className="public-hero-sub">
            把網站問題整理成可以執行的改善順序。
            整合全站爬蟲、四維靜態掃描與 LLM Agent 行為測試，
            為你授權的網站產出可互動報告與 Word 文件，
            並輸出結構化 Prompt 帶去 ChatGPT / Claude 取得修補方向。
          </p>
          <div className="public-hero-actions">
            <NavLink to="/login" className="public-cta-primary">登入進行詳細檢查 →</NavLink>
            <NavLink to="/free-tools" className="public-cta-ghost">免登入先試單頁檢查</NavLink>
          </div>
        </div>
      </section>

      <section className="public-section">
        <header className="public-section-head">
          <h2>安全邊界</h2>
          <p>不是文宣口號，每一項都對應實際程式碼</p>
        </header>
        <div className="public-feature-grid">
          <article className="public-feature-card">
            <div className="public-feature-icon">🔐</div>
            <h3 className="public-feature-title">授權確認</h3>
            <p className="public-feature-desc">
              每次任務記錄 IP、時間、User-Agent 與授權勾選狀態；第三方或敏感網域要求二次確認。
            </p>
          </article>
          <article className="public-feature-card">
            <div className="public-feature-icon">🌐</div>
            <h3 className="public-feature-title">同網域邏輯</h3>
            <p className="public-feature-desc">
              爬蟲與 finding 證據只限授權目標的同網域頁面，不會跨域追蹤或污染他站。
            </p>
          </article>
          <article className="public-feature-card">
            <div className="public-feature-icon">🛡️</div>
            <h3 className="public-feature-title">SSRF 應用層防護</h3>
            <p className="public-feature-desc">
              入口、轉址、子資源與 WebSocket 均檢查公開位址；正式環境仍須搭配出站網路政策。
            </p>
          </article>
          <article className="public-feature-card">
            <div className="public-feature-icon">👀</div>
            <h3 className="public-feature-title">預設被動模式</h3>
            <p className="public-feature-desc">
              Phase 1 不做破壞性或主動式漏洞攻擊；主動模式需額外勾選且記入稽核軌跡。
            </p>
          </article>
        </div>
      </section>

      <section className="public-section">
        <header className="public-section-head">
          <h2>平台規模</h2>
          <p>不是 demo 玩具，是真實量產規格</p>
        </header>
        <div className="project-stats-grid">
          {PROJECT_PLATFORM_STATS.map((s) => (
            <div key={s.label} className="project-stat-card">
              <div className="project-stat-value">{s.value}</div>
              <div className="project-stat-label">{s.label}</div>
              <div className="project-stat-hint">{s.hint}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="public-section">
        <header className="public-section-head">
          <h2>它怎麼運作</h2>
          <p>輸入網址 → 爬蟲 → 四維掃描 → 互動報告</p>
        </header>
        <ProjectScanDemo />
      </section>

      <section className="public-section">
        <header className="public-section-head">
          <h2>核心功能</h2>
          <p>從爬蟲到 LLM Agent，端到端解決方案</p>
        </header>
        <div className="public-feature-grid">
          {features.map((f) => (
            <article key={f.id} className="public-feature-card">
              <div className="public-feature-icon">{f.icon || "✨"}</div>
              <h3 className="public-feature-title">{f.title}</h3>
              <p className="public-feature-desc">{f.description}</p>
            </article>
          ))}
          {features.length === 0 && (
            <p className="public-empty">尚未設定功能介紹。</p>
          )}
        </div>
      </section>

      {milestones.length > 0 && (
        <section className="public-section">
          <header className="public-section-head">
            <h2>開發歷程</h2>
            <p>從 MVP 到上線的關鍵里程碑</p>
          </header>
          <ol className="project-timeline">
            {milestones.map((m, idx) => (
              <li key={m.id} className={`project-timeline-item ${idx === 0 ? "is-first" : ""}`}>
                <div className="project-timeline-marker">
                  <span className="project-timeline-icon">{m.icon || "🚩"}</span>
                </div>
                <div className="project-timeline-body">
                  <div className="project-timeline-date">
                    {new Date(m.date).toLocaleDateString("zh-Hant", { year: "numeric", month: "long", day: "numeric" })}
                  </div>
                  <div className="project-timeline-title">{m.title}</div>
                  {m.description && (
                    <p className="project-timeline-desc">{m.description}</p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

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

function TeamMemberCard({ member }) {
  const m = member;
  return (
    <article className="public-team-card-pro">
      <header className="public-team-card-head">
        <div className="public-team-avatar-wrap">
          <span className="public-team-avatar-ring" aria-hidden="true" />
          <span className="public-team-avatar-glyph">{m.avatar_emoji || "🧑"}</span>
        </div>
        <div className="public-team-card-meta">
          <div className="public-team-name">{m.name}</div>
          <div className="public-team-role">{m.role}</div>
          {m.bio && <p className="public-team-bio">{m.bio}</p>}
        </div>
      </header>

      {Array.isArray(m.skill_levels) && m.skill_levels.length > 0 && (
        <div className="public-team-skill-bars">
          <div className="public-team-block-label">⚡ 技能熟練度</div>
          {m.skill_levels.map((s) => (
            <div key={s.name} className="public-team-skill-row">
              <div className="public-team-skill-row-head">
                <span>{s.name}</span>
                <span className="public-team-skill-pct">{s.level}%</span>
              </div>
              <div className="public-team-skill-track">
                <div
                  className="public-team-skill-fill"
                  style={{ width: `${Math.max(0, Math.min(100, s.level))}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {Array.isArray(m.contributions) && m.contributions.length > 0 && (
        <div className="public-team-contrib">
          <div className="public-team-contrib-label">🎯 負責項目</div>
          <ul className="public-team-contrib-list">
            {m.contributions.map((c, i) => (
              <li key={i}>
                <span className="public-team-contrib-bullet" aria-hidden="true" />
                <div>
                  <div className="public-team-contrib-title">{c.title}</div>
                  {c.desc && <div className="public-team-contrib-desc">{c.desc}</div>}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {Array.isArray(m.skills) && m.skills.length > 0 && (
        <div className="public-team-skills">
          <div className="public-team-block-label public-team-skills-label">🧩 技術棧</div>
          {m.skills.map((s) => (
            <span key={s} className="public-team-skill-chip">{s}</span>
          ))}
        </div>
      )}

      {m.github_url && (
        <div className="public-team-links">
          <a href={m.github_url} target="_blank" rel="noopener noreferrer">
            🐙 GitHub
          </a>
        </div>
      )}
    </article>
  );
}

function TeamPage() {
  const [members, setMembers] = useState([]);
  useEffect(() => {
    api.get("/content/team/").then((r) => setMembers(r.data.members || [])).catch(() => {});
  }, []);
  return (
    <div className="public-page">
      <section className="public-hero compact">
        <div className="public-hero-bg" aria-hidden="true">
          <span className="hero-orb hero-orb-1" />
          <span className="hero-orb hero-orb-2" />
          <span className="hero-orb hero-orb-3" />
        </div>
        <div className="public-hero-content">
          <span className="public-hero-eyebrow">TEAM · 團隊</span>
          <h1 className="public-hero-title">
            打造 Argus 的<span className="hero-grad">團隊</span>
          </h1>
          <p className="public-hero-sub">
            {members.length} 位成員跨領域協作，從 Playwright 爬蟲、LLM Agent
            到 Tailwind UI 與 Docker 部署，一手包辦。
          </p>
          <div className="public-team-stats">
            <div className="public-team-stat">
              <div className="public-team-stat-value">{members.length}</div>
              <div className="public-team-stat-label">核心成員</div>
            </div>
            <div className="public-team-stat">
              <div className="public-team-stat-value">8</div>
              <div className="public-team-stat-label">Django apps</div>
            </div>
            <div className="public-team-stat">
              <div className="public-team-stat-value">249+</div>
              <div className="public-team-stat-label">自動化測試</div>
            </div>
          </div>
        </div>
      </section>

      <section className="public-section">
        <div className="public-team-grid-pro">
          {members.map((m) => (
            <TeamMemberCard key={m.id} member={m} />
          ))}
          {members.length === 0 && (
            <p className="public-empty">尚未設定團隊成員。</p>
          )}
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
    a: "每爬一個頁面 10 coin。建立掃描時依「最大頁數」預扣，完成後依實際頁數退回未使用的部分。",
  },
  {
    q: "支援哪些付款方式？",
    a: "目前為模擬付款（點選即入帳，供示範用）。正式上線後將串接綠界 / 藍新 / Stripe 等金流。",
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
            每爬一頁 10 coin，新會員每月自動贈送 200 coin；買越多越划算，
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
          <p>我們、自己做、市面其他工具的對比</p>
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
  TeamPage,
  PurchasePage,
  FreeToolsPage,
  DownloadPage,
};
