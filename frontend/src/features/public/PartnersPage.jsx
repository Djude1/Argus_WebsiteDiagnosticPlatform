import { useRef, useState } from "react";
import { NavLink } from "react-router-dom";

import { api } from "../../api";
import { apiErrorMessage } from "../../shared/AppShared.jsx";
import { TURNSTILE_FIELD, TurnstileWidget, useTurnstileConfig } from "../../shared/TurnstileWidget";

// 商業合作（/partners）：讓潛在合作方看懂「可以怎麼合作、客戶會得到什麼、如何開始討論」。
// 內容只寫目前真的做得到的事：白牌、固定分潤與 MCP 以外的系統整合都寫成「依需求討論」。

const PARTNER_TYPES = [
  {
    value: "agency",
    title: "網站開發與數位代理",
    desc: "交付網站前用 Argus 產出健檢報告，列出 SEO、AEO、GEO、資安與使用體驗的待修項目，作為驗收與後續優化提案的依據。",
  },
  {
    value: "operations",
    title: "維運與技術服務",
    desc: "對已上線的網站定期掃描，用同網址的分數歷史追蹤改善幅度，把新出現的問題整理成維運待辦。",
  },
  {
    value: "platform",
    title: "平台與技術合作",
    desc: "探討把診斷結果放進你的平台或交付流程。訂閱會員已可透過 MCP 讓 AI 工具直接建立掃描、讀取結果；更深的整合方式依實際需求評估。",
  },
];

const PARTNER_OUTCOMES = [
  { label: "發現的問題", desc: "每一項都標出嚴重度、所屬維度與受影響的頁面，客戶一眼看懂問題在哪。" },
  { label: "判斷依據", desc: "附規則編號與證據（回應標頭、HTML 片段、截圖標記位置），團隊可以直接複查。" },
  { label: "處理順序", desc: "依嚴重度與影響排出優先處理項目，並附修正方向；Word 報告附報告編號，可在「報告查驗」核對真偽。" },
];

const PARTNER_STEPS = [
  { title: "提出需求", desc: "填寫下方表單，說明你的服務與客戶類型。" },
  { title: "確認情境與授權範圍", desc: "釐清要掃描的網站、頻率，以及網站擁有者的授權方式。" },
  { title: "小範圍試行", desc: "先挑幾個網站實際掃描，確認報告符合你的交付需求。" },
  { title: "商議合作方式", desc: "依使用量與整合深度討論合作內容與價格。" },
];

const PARTNER_FAQ = [
  {
    q: "可以掃描任何客戶的網站嗎？",
    a: "只能掃描你擁有或已取得授權的網站；每次建立掃描都要勾選授權確認。主動式資安測試另需通過網域所有權驗證。",
  },
  {
    q: "價格怎麼計算？",
    a: "一般使用依頁數與勾選的維度計點（每頁每維度 2 coin）。批量使用與合作價格依需求討論。",
  },
  {
    q: "可以整合到我們的系統或做成自有品牌嗎？",
    a: "訂閱會員可透過 MCP 接入，讓 Claude Code、Codex 等 AI 工具直接建立掃描與讀取結果；目前沒有其他公開 API 或白牌版本。若有更深的整合需求，請在表單中說明情境，我們會評估可行性後回覆。",
  },
  {
    q: "報告可以直接交給我的客戶嗎？",
    a: "可以。Word 報告附報告編號，客戶可在「報告查驗」頁輸入編號，確認報告確實由 Argus 出具。",
  },
];

const EMPTY_FORM = {
  name: "",
  company: "",
  email: "",
  partner_type: "agency",
  message: "",
  phone: "",
  site_count: "",
  website: "",
};

function PartnerInquiryForm() {
  const [form, setForm] = useState(EMPTY_FORM);
  const [state, setState] = useState({ busy: false, done: "", error: "", fieldErrors: {} });
  const turnstile = useTurnstileConfig();
  const [captcha, setCaptcha] = useState("");
  const captchaRef = useRef(null);
  const captchaBlocking = turnstile.loading || (turnstile.enabled && !captcha);

  function update(key) {
    return (e) => setForm((prev) => ({ ...prev, [key]: e.target.value }));
  }

  async function submit(e) {
    e.preventDefault();
    setState({ busy: true, done: "", error: "", fieldErrors: {} });
    try {
      const body = turnstile.enabled ? { ...form, [TURNSTILE_FIELD]: captcha } : form;
      const res = await api.post("/content/partner-inquiries/", body);
      setState({ busy: false, done: res.data?.detail || "已收到你的洽談需求。", error: "", fieldErrors: {} });
      setForm(EMPTY_FORM);
    } catch (err) {
      const data = err?.response?.status === 400 ? err.response.data : null;
      setState({
        busy: false,
        done: "",
        error: data ? "請檢查標示的欄位。" : apiErrorMessage(err, "送出失敗，請稍後再試。"),
        fieldErrors: data || {},
      });
    } finally {
      // 人機驗證 token 只能用一次，不論成功失敗都重設取得新的
      captchaRef.current?.reset();
    }
  }

  if (state.done) {
    return (
      <div className="partners-form-done" role="status">
        <h3>已收到你的洽談需求</h3>
        <p>{state.done}</p>
        <button type="button" className="partners-link" onClick={() => setState({ busy: false, done: "", error: "", fieldErrors: {} })}>
          再送一份
        </button>
      </div>
    );
  }

  const fieldError = (key) => {
    const value = state.fieldErrors[key];
    return value ? <span className="partners-field-error">{Array.isArray(value) ? value[0] : value}</span> : null;
  };

  return (
    <form className="insight-tool-card partners-form" onSubmit={submit} noValidate>
      <div className="partners-form-grid">
        <label className="insight-field">
          <span>姓名 *</span>
          <input value={form.name} onChange={update("name")} maxLength={80} required autoComplete="name" />
          {fieldError("name")}
        </label>
        <label className="insight-field">
          <span>公司 *</span>
          <input value={form.company} onChange={update("company")} maxLength={120} required autoComplete="organization" />
          {fieldError("company")}
        </label>
        <label className="insight-field">
          <span>工作信箱 *</span>
          <input type="email" value={form.email} onChange={update("email")} required autoComplete="email" />
          {fieldError("email")}
        </label>
        <label className="insight-field">
          <span>合作類型 *</span>
          <select value={form.partner_type} onChange={update("partner_type")}>
            {PARTNER_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.title}</option>
            ))}
            <option value="other">其他</option>
          </select>
        </label>
        <label className="insight-field">
          <span>電話（選填）</span>
          <input value={form.phone} onChange={update("phone")} maxLength={40} autoComplete="tel" />
        </label>
        <label className="insight-field">
          <span>預估網站數量（選填）</span>
          <input value={form.site_count} onChange={update("site_count")} maxLength={40} placeholder="例：每月 5–10 個" />
        </label>
      </div>
      <label className="insight-field">
        <span>需求說明 *</span>
        <textarea
          value={form.message}
          onChange={update("message")}
          rows={5}
          maxLength={2000}
          required
          placeholder="你的服務內容、客戶類型，以及希望 Argus 在流程中的哪個環節幫上忙"
        />
        {fieldError("message")}
      </label>
      {/* 給機器人填的誘餌欄位：一般使用者看不到。標籤與 name 刻意不用「網站／公司／網址」等字眼，
          避免瀏覽器自動填入；即使被填，後端也只標成疑似垃圾訊息，不會丟棄。 */}
      <label className="partners-hp" aria-hidden="true">
        請勿填寫此欄
        <input
          tabIndex={-1}
          name="argus_hp_field"
          autoComplete="off"
          value={form.website}
          onChange={update("website")}
        />
      </label>
      {turnstile.enabled && (
        <TurnstileWidget ref={captchaRef} siteKey={turnstile.siteKey} action="contact" onToken={setCaptcha} />
      )}
      {state.error && <p className="partners-form-error" role="alert">{state.error}</p>}
      <div className="partners-form-actions">
        <button type="submit" className="public-cta-primary" disabled={state.busy || captchaBlocking}>
          {state.busy ? "送出中…" : "送出洽談需求"}
        </button>
        <p className="partners-form-note">送出的資料只用於聯繫這次合作洽談。</p>
      </div>
    </form>
  );
}

function PartnersPage() {
  return (
    <div className="public-page partners-page">
      <section className="public-hero partners-hero">
        <div className="public-hero-bg" aria-hidden="true">
          <span className="hero-orb hero-orb-1" />
        </div>
        <div className="public-hero-content partners-hero-grid">
          <div>
            <span className="public-hero-eyebrow">PARTNERS · 商業合作</span>
            <h1 className="public-hero-title">
              讓網站診斷，成為你<span className="hero-grad">服務客戶</span>的一部分。
            </h1>
            <p className="public-hero-sub">
              與 Argus 探討網站建置、交付與維運中的診斷需求，把發現的問題整理成客戶看得懂、團隊能採取行動的結果。
            </p>
            <div className="partners-hero-actions">
              <a href="#partner-form" className="public-cta-primary">洽談合作</a>
              <NavLink to="/project" className="partners-link">了解 Argus 如何運作 →</NavLink>
            </div>
          </div>
          <figure className="home-evidence-sample partners-report" aria-label="報告中一筆問題的示意">
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
          <h2>合作方式</h2>
          <p>依你的服務型態，Argus 放進流程的位置不同</p>
        </header>
        <ol className="partners-types">
          {PARTNER_TYPES.map((t) => (
            <li key={t.value}>
              <h3>{t.title}</h3>
              <p>{t.desc}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="public-section">
        <header className="public-section-head">
          <h2>你的客戶會拿到什麼</h2>
          <p>一份能直接拿來討論與修正的報告，而不是一句「網站品質待提升」</p>
        </header>
        <dl className="partners-outcomes">
          {PARTNER_OUTCOMES.map((o) => (
            <div key={o.label}>
              <dt>{o.label}</dt>
              <dd>{o.desc}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="public-section">
        <header className="public-section-head">
          <h2>合作流程</h2>
        </header>
        <ol className="partners-steps">
          {PARTNER_STEPS.map((s, i) => (
            <li key={s.title}>
              <span className="partners-step-no">{i + 1}</span>
              <h3>{s.title}</h3>
              <p>{s.desc}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="public-section">
        <header className="public-section-head">
          <h2>常見問題</h2>
        </header>
        <div className="public-faq">
          {PARTNER_FAQ.map((item) => (
            <details key={item.q} className="public-faq-item">
              <summary>{item.q}</summary>
              <p>{item.a}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="public-section" id="partner-form">
        <header className="public-section-head">
          <h2>洽談合作</h2>
          <p>留下聯絡方式與需求，我們會以 Email 回覆</p>
        </header>
        <PartnerInquiryForm />
      </section>
    </div>
  );
}

export default PartnersPage;
export { PartnersPage };
