import { useId, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../../api";
import { ArgusMark } from "../../components/brand/ArgusMark";
import { IrisScore } from "../../components/brand/IrisScore";
import { PublicHero } from "../../components/public/PublicHero";
import { ClockIcon, MagnifierIcon, ShieldIcon } from "../../shared/LineIcons";
import { apiErrorMessage } from "../../shared/AppShared";

const TOOLS = [
  { key: "scan", label: "單頁檢查", Icon: MagnifierIcon },
  { key: "speed", label: "網站測速", Icon: ClockIcon },
  { key: "phish", label: "釣魚偵測", Icon: ShieldIcon },
];

const SEVERITY_LABELS = { critical: "嚴重", high: "高", medium: "中", low: "低", info: "提示" };

// 快速檢查的維度 key → 品牌維度色（aeo_geo 合併維度用 GEO 色）
const CATEGORY_TONE = { seo: "seo", security: "security", aeo_geo: "geo", aeo: "aeo", geo: "geo", ux: "ux" };

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

function SeverityBadge({ severity }) {
  if (!severity) return null;
  return <span className={`severity ${severity}`}>{SEVERITY_LABELS[severity] || severity}</span>;
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

/** 結果區載入中：品牌標誌掃描動畫＋骨架，讓使用者知道正在跑、大概會長什麼樣。 */
function ResultLoading({ label }) {
  return (
    <div className="insight-loading" role="status" aria-live="polite">
      <div className="insight-loading-head">
        <ArgusMark size={40} scanning />
        <span>
          <strong>{label}</strong>
          <span className="insight-loading-sub">通常幾秒內完成</span>
        </span>
      </div>
      <span className="insight-skeleton is-wide" />
      <span className="insight-skeleton" />
      <span className="insight-skeleton is-short" />
    </div>
  );
}

/** 尚未執行：預告會輸出什麼，而不是一塊空白。 */
function ResultEmpty({ title, items }) {
  return (
    <div className="insight-empty">
      <IrisScore score={null} size={72} />
      <div>
        <strong>{title}</strong>
        <ul className="insight-empty-list">
          {items.map((item) => <li key={item}>{item}</li>)}
        </ul>
      </div>
    </div>
  );
}

function AuthorizationCheck({ checked, onChange, children }) {
  return (
    <label className="insight-check">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>{children}</span>
    </label>
  );
}

function QuickScanTool({ initialUrl }) {
  // 導流 CTA「登入建立完整掃描」要用
  const navigate = useNavigate();
  const [form, setForm] = useState({ url: initialUrl, authorization_confirmed: false });
  const quick = useInsightTool("/insights/quick-scan/");
  const fieldId = useId();

  const submit = (event) => {
    event.preventDefault();
    quick.run(form, "單頁快速檢查失敗，請確認網址可公開連線。");
  };

  return (
    <div className="insight-tool-layout">
      <form className="insight-tool-card" onSubmit={submit}>
        <h3 className="insight-card-title">輸入要檢查的網址</h3>
        <p className="insight-card-desc">分析一個頁面的 HTML 與回應標頭，給 SEO／資安／AEO·GEO 分數與重點問題。</p>
        <div className="insight-field">
          <label htmlFor={fieldId}>網址</label>
          <input
            id={fieldId}
            className="input insight-url-input"
            value={form.url}
            onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
            placeholder="https://example.com/"
            inputMode="url"
            spellCheck={false}
            required
          />
          {initialUrl && !quick.result && (
            <span className="insight-field-hint">已帶入首頁輸入的網址，勾選下方聲明即可開始。</span>
          )}
        </div>
        <AuthorizationCheck
          checked={form.authorization_confirmed}
          onChange={(checked) => setForm((f) => ({ ...f, authorization_confirmed: checked }))}
        >
          我確認此頁面可公開檢測，或我擁有分析授權。
        </AuthorizationCheck>
        {quick.error && <div className="insight-error" role="alert">{quick.error}</div>}
        <button type="submit" className="public-cta public-cta-primary insight-submit" disabled={quick.loading}>
          {quick.loading ? "檢查中..." : "開始單頁檢查"}
        </button>
      </form>

      <div className="insight-result-card" aria-live="polite">
        {quick.loading ? (
          <ResultLoading label="正在檢查這個頁面…" />
        ) : !quick.result ? (
          <ResultEmpty
            title="會輸出哪些結果"
            items={["整體分數與 SEO／資安／AEO·GEO 三維分數", "依嚴重度排序的重點問題清單", "完整掃描可取得的修正內容"]}
          />
        ) : (
          <>
            <div className="insight-score-row">
              <IrisScore score={quick.result.overall_score} size={96} caption="整體" />
              <div className="insight-score-meta">
                <div className="insight-result-title">{quick.result.final_url}</div>
                <div className="insight-result-sub">單頁快速檢查（不含多頁爬蟲 / Playwright）</div>
              </div>
            </div>
            <ul className="insight-dims">
              {quick.result.categories.map((c) => (
                <li key={c.key} className={`insight-dim cat-${CATEGORY_TONE[c.key] || "seo"}`}>
                  <span className="insight-dim-label">{c.label}</span>
                  <span className="insight-dim-track" aria-hidden="true">
                    <span className="insight-dim-fill" style={{ width: `${Math.max(0, Math.min(100, c.score))}%` }} />
                  </span>
                  <strong className="insight-dim-score ag-num">{c.score}</strong>
                </li>
              ))}
            </ul>
            {quick.result.findings.length > 0 ? (
              <ul className="insight-finding-list">
                {quick.result.findings.map((f, idx) => (
                  <li key={`${f.title}-${idx}`}>
                    <SeverityBadge severity={f.severity} />
                    <span className="insight-finding-body">
                      <strong>{f.title}</strong>
                      <span>{f.detail}</span>
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="insight-success">單頁檢查未發現明顯問題。</div>
            )}
            <p className="insight-note">{quick.result.note}</p>
            {/* 導流 CTA（修正產出票06）：只講完整掃描的加值與入口，
                不提供任何免費產生——修正產出對應的是一份付費掃描結果。 */}
            <div className="insight-cta">
              <div>
                <strong>完整掃描可獲得可直接貼上的修正內容</strong>
                <span>
                  JSON-LD、Open Graph＋meta、llms.txt 與 FAQ Schema，
                  以網站實際內容產生、可直接複製採用；付費掃描附贈 1 次產生額度。
                </span>
              </div>
              <button type="button" className="public-cta public-cta-accent" onClick={() => navigate("/login")}>
                登入建立完整掃描
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function SpeedTool() {
  const [form, setForm] = useState({ url: "", authorization_confirmed: false });
  const speed = useInsightTool("/insights/speed-test/");
  const fieldId = useId();

  const submit = (event) => {
    event.preventDefault();
    speed.run(form, "測速失敗，請確認網址可公開連線。");
  };

  const metrics = speed.result?.metrics;
  return (
    <div className="insight-tool-layout">
      <form className="insight-tool-card" onSubmit={submit}>
        <h3 className="insight-card-title">輸入要測速的網址</h3>
        <p className="insight-card-desc">單一 URL、單次請求，參考 PageSpeed / Lighthouse 的效能思路。</p>
        <div className="insight-field">
          <label htmlFor={fieldId}>網址</label>
          <input
            id={fieldId}
            className="input insight-url-input"
            value={form.url}
            onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
            placeholder="https://example.com/"
            inputMode="url"
            spellCheck={false}
            required
          />
        </div>
        <AuthorizationCheck
          checked={form.authorization_confirmed}
          onChange={(checked) => setForm((f) => ({ ...f, authorization_confirmed: checked }))}
        >
          我確認此頁面可公開測速，或我擁有分析授權。
        </AuthorizationCheck>
        {speed.error && <div className="insight-error" role="alert">{speed.error}</div>}
        <button type="submit" className="public-cta public-cta-primary insight-submit" disabled={speed.loading}>
          {speed.loading ? "測速中..." : "開始測速"}
        </button>
      </form>

      <div className="insight-result-card" aria-live="polite">
        {speed.loading ? (
          <ResultLoading label="正在量測回應時間…" />
        ) : !speed.result ? (
          <ResultEmpty
            title="會輸出哪些結果"
            items={["效能分數與 TTFB、傳輸量", "阻塞 script、圖片 lazy loading", "快取與壓縮建議"]}
          />
        ) : (
          <>
            <div className="insight-score-row">
              <IrisScore score={speed.result.score} size={96} caption="效能" />
              <div className="insight-score-meta">
                <div className="insight-result-title">{speed.result.final_url}</div>
                <div className="insight-result-sub">{speed.result.source}</div>
              </div>
            </div>
            <dl className="insight-metrics-grid">
              <div><dt>TTFB</dt><dd className="ag-num">{metrics.ttfb_ms}<small> ms</small></dd></div>
              <div><dt>傳輸量</dt><dd className="ag-num">{metrics.transfer_kb}<small> KB</small></dd></div>
              <div><dt>阻塞 script</dt><dd className="ag-num">{metrics.blocking_scripts}</dd></div>
              <div><dt>圖片</dt><dd className="ag-num">{metrics.images}</dd></div>
            </dl>
            <p className="insight-note">{speed.result.core_web_vitals_note}</p>
            {speed.result.findings.length > 0 ? (
              <ul className="insight-finding-list">
                {speed.result.findings.map((f, idx) => (
                  <li key={`${f.title}-${idx}`}>
                    <SeverityBadge severity={f.severity} />
                    <span className="insight-finding-body">
                      <strong>{f.title}</strong>
                      <span>{f.description}</span>
                    </span>
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
  );
}

function RiskResult({ result, children }) {
  const score = Math.max(0, Math.min(100, Number(result.risk_score) || 0));
  return (
    <div className={`insight-risk-result risk-${result.risk_level || "minimal"}`}>
      <div className="insight-risk-head">
        <span className="insight-risk-score ag-num">{result.risk_score}<small>/100</small></span>
        <RiskLevelBadge level={result.risk_level} />
      </div>
      <div className="insight-risk-meter" aria-hidden="true">
        <span style={{ width: `${score}%` }} />
      </div>
      <p className="insight-risk-reco">{result.recommendation}</p>
      {children}
      <ul className="insight-feature-list">
        {result.features.slice(0, 5).map((f, idx) => (
          <li key={`${f.title}-${idx}`}>
            <strong>{f.title}</strong>
            <code>{f.evidence}</code>
          </li>
        ))}
      </ul>
    </div>
  );
}

function PhishingTool() {
  const [urlValue, setUrlValue] = useState("");
  const [emailValue, setEmailValue] = useState("");
  const urlCheck = useInsightTool("/insights/phishing-url/");
  const emailCheck = useInsightTool("/insights/phishing-email/");
  const urlId = useId();
  const emailId = useId();

  return (
    <div className="insight-two-col">
      <form
        className="insight-tool-card"
        onSubmit={(event) => {
          event.preventDefault();
          urlCheck.run({ url: urlValue }, "URL 風險分析失敗。");
        }}
      >
        <h3 className="insight-card-title">網址安全檢測（防釣魚）</h3>
        <p className="insight-card-desc">貼上可疑連結，檢查網域、路徑與註冊時間等特徵。</p>
        <div className="insight-field">
          <label htmlFor={urlId}>可疑連結</label>
          <input
            id={urlId}
            className="input insight-url-input"
            value={urlValue}
            onChange={(e) => setUrlValue(e.target.value)}
            placeholder="https://secure-login.example/verify"
            spellCheck={false}
            required
          />
        </div>
        {urlCheck.error && <div className="insight-error" role="alert">{urlCheck.error}</div>}
        <button type="submit" className="public-cta public-cta-primary insight-submit" disabled={urlCheck.loading}>
          {urlCheck.loading ? "分析中..." : "分析 URL"}
        </button>
        {urlCheck.result && <RiskResult result={urlCheck.result} />}
      </form>

      <form
        className="insight-tool-card"
        onSubmit={(event) => {
          event.preventDefault();
          emailCheck.run({ raw_email: emailValue }, "郵件風險分析失敗。");
        }}
      >
        <h3 className="insight-card-title">郵件詐騙檢測（防釣魚信）</h3>
        <p className="insight-card-desc">貼上 .eml 或原始信件內容，檢查寄件網域、Reply-To 與誘導用語。</p>
        <div className="insight-field">
          <label htmlFor={emailId}>.eml / 原始信件內容</label>
          <textarea
            id={emailId}
            className="input insight-textarea"
            value={emailValue}
            onChange={(e) => setEmailValue(e.target.value)}
            placeholder={"From: notice@example.com\nAuthentication-Results: ...\n\n請立即驗證帳號..."}
            rows={8}
            required
          />
        </div>
        {emailCheck.error && <div className="insight-error" role="alert">{emailCheck.error}</div>}
        <button type="submit" className="public-cta public-cta-primary insight-submit" disabled={emailCheck.loading}>
          {emailCheck.loading ? "分析中..." : "分析郵件"}
        </button>
        {emailCheck.result && (
          <RiskResult result={emailCheck.result}>
            <div className="insight-email-meta">
              <span>From <code>{emailCheck.result.from_domain || "未解析"}</code></span>
              <span>連結數 <code>{emailCheck.result.url_count}</code></span>
            </div>
          </RiskResult>
        )}
      </form>
    </div>
  );
}

const TOOL_HEADS = {
  scan: {
    title: "單頁快速檢查",
    desc: "輸入一個網址，立即看單頁體檢分數與重點問題；完整多頁＋AI 深掃請登入後到「掃描」。",
  },
  speed: {
    title: "網站測速分析",
    desc: "單一 URL、單次請求，不扣 coin，不啟動全站爬蟲。",
  },
  phish: {
    title: "可疑網址 / 詐騙郵件檢測",
    desc: "本機特徵分類器判斷是否可能是釣魚／詐騙，內容不外送大模型 API。",
  },
};

export function FreeToolsPage() {
  const [searchParams] = useSearchParams();
  const initialUrl = searchParams.get("url") || "";
  const [tool, setTool] = useState("scan");
  const tabsId = useId();

  return (
    <div className="public-page free-tools-page">
      <PublicHero
        eyebrow="Quick check · 快速檢查"
        title={<>先用<em>快速檢查</em>初步判斷</>}
      >
        <p>
          <strong>免登入、不扣點數、即時出結果。</strong>
          釣魚網址與郵件判斷使用本機特徵分類器，不把內容送到大模型 API。
        </p>
      </PublicHero>

      <section className="public-section insight-section">
        <div className="insight-tabs" role="tablist" aria-label="快速檢查工具">
          {TOOLS.map(({ key, label, Icon }) => (
            <button
              key={key}
              type="button"
              role="tab"
              id={`${tabsId}-tab-${key}`}
              aria-selected={tool === key}
              aria-controls={`${tabsId}-panel-${key}`}
              className={`insight-tab ${tool === key ? "active" : ""}`}
              onClick={() => setTool(key)}
            >
              <Icon className="insight-tab-icon" />
              {label}
            </button>
          ))}
        </div>

        {/* 三個工具都保持掛載、只隱藏非目前分頁：切換分頁不會丟掉已輸入的內容與結果 */}
        {TOOLS.map(({ key }) => (
          <div
            key={key}
            className="insight-panel"
            role="tabpanel"
            id={`${tabsId}-panel-${key}`}
            aria-labelledby={`${tabsId}-tab-${key}`}
            hidden={tool !== key}
          >
            <header className="insight-panel-head">
              <h2>{TOOL_HEADS[key].title}</h2>
              <p>{TOOL_HEADS[key].desc}</p>
            </header>
            {key === "scan" && <QuickScanTool initialUrl={initialUrl} />}
            {key === "speed" && <SpeedTool />}
            {key === "phish" && <PhishingTool />}
          </div>
        ))}
      </section>
    </div>
  );
}

export default FreeToolsPage;
