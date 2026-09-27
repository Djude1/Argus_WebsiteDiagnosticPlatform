import { useNavigate } from "react-router-dom";

import { ArgusMark } from "../../components/brand/ArgusMark";
import { PublicHero, PublicSection } from "../../components/public/PublicHero";
import { PublicFaq } from "../../components/public/PublicFaq";
import { CoinIcon, LayersIcon, ScoreIcon } from "../../shared/LineIcons";

// 計費說明三步驟：與 FAQ／結帳頁同一套規則，只換成一眼看懂的排版
const PRICING_STEPS = [
  {
    Icon: LayersIcon,
    title: "只勾需要的維度",
    value: "2",
    unit: "coin／頁／維度",
    desc: "五維全選＝每頁 10 coin；只看 SEO 就只算 SEO。",
  },
  {
    Icon: ScoreIcon,
    title: "先預扣、再退回",
    value: "100%",
    unit: "未用點數退回",
    desc: "建立時依最大頁數預扣，完成後依實際頁數退回；失敗或取消全額退回。",
  },
  {
    Icon: CoinIcon,
    title: "每月贈點、永久有效",
    value: "200",
    unit: "coin／月",
    desc: "登入後每月自動贈送；已購點數不會過期。",
  },
];

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
    a: "目前為模擬付款（點選即入帳，供示範用）。正式上線後將串接綠界 / 藍新 / Stripe 等金流。",
  },
  {
    q: "可以退費嗎？",
    a: "如有特殊狀況請聯絡管理員，由 admin 在後台手動退費。掃描失敗或被取消時，系統會自動全額退回預扣的點數。",
  },
];

const COMPARE_ROWS = [
  { feature: "全站爬蟲（同網域、深度 3、最多 50 頁）", self: "技術門檻高", competitor: "通常另計" },
  { feature: "SEO + AEO + GEO + 資安四維掃描", self: "工具多套需自己整合", competitor: "多為單一維度" },
  { feature: "AI Agent 擬真使用者 UX 測試", self: "無", competitor: "罕見" },
  { feature: "可互動報告（截圖紅框 + 雙向跳轉）", self: "Lighthouse 純文字", competitor: "PDF 為主" },
  { feature: "Word 報告自動匯出", self: "手寫", competitor: "額外加購" },
  { feature: "結構化問題 Prompt 帶去 ChatGPT 修", self: "需要自己整理", competitor: "—" },
  { feature: "按頁付費（用多少付多少）", self: "—", competitor: "月費綁約" },
  { feature: "首月免費 200 coin", self: "—", competitor: "需信用卡綁定試用" },
];

function CheckMark() {
  return (
    <span className="compare-check">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.2 4.2L19 7" /></svg>
      <span className="sr-only">支援</span>
    </span>
  );
}

export function PurchasePage() {
  const navigate = useNavigate();
  return (
    <div className="public-page">
      <PublicHero
        eyebrow="Pricing · 為什麼選 Argus"
        title={<><em>按頁付費</em>，永久有效</>}
        actions={(
          <button type="button" className="public-cta public-cta-primary" onClick={() => navigate("/billing")}>
            看方案 + 開始結帳 →
          </button>
        )}
      >
        <p>
          掃描按維度計費，只勾選需要的項目；新會員每月自動贈送 200 coin；買越多越划算，
          點數不會過期，失敗或取消自動全額退回。
        </p>
      </PublicHero>

      <PublicSection eyebrow="How billing works" title="計費方式" description="三件事講完：怎麼算、怎麼退、送多少。">
        <ol className="pricing-steps">
          {PRICING_STEPS.map(({ Icon, title, value, unit, desc }, idx) => (
            <li key={title} className="pricing-step">
              <div className="pricing-step-head">
                <span className="pricing-step-icon"><Icon /></span>
                <span className="pricing-step-no ag-num">0{idx + 1}</span>
              </div>
              <h3 className="pricing-step-title">{title}</h3>
              <p className="pricing-step-value">
                <span className="ag-num">{value}</span>
                <small>{unit}</small>
              </p>
              <p className="pricing-step-desc">{desc}</p>
            </li>
          ))}
        </ol>
      </PublicSection>

      <PublicSection eyebrow="Compare" title="為什麼選 Argus" description="Argus、自己做、市面工具，三者比一比。">
        <div className="compare-wrap">
          <table className="compare-table">
            <thead>
              <tr>
                <th scope="col" className="compare-feature">功能</th>
                <th scope="col" className="compare-argus">
                  <span className="compare-brand">
                    <ArgusMark size={20} />
                    ARGUS
                  </span>
                </th>
                <th scope="col">自己做</th>
                <th scope="col">競品工具</th>
              </tr>
            </thead>
            <tbody>
              {COMPARE_ROWS.map((row) => (
                <tr key={row.feature}>
                  <th scope="row" className="compare-feature">{row.feature}</th>
                  <td className="compare-argus" data-label="Argus"><CheckMark /></td>
                  <td className="compare-cell" data-label="自己做">{row.self}</td>
                  <td className="compare-cell" data-label="競品工具">{row.competitor}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </PublicSection>

      <PublicSection eyebrow="FAQ" title="常見問題">
        <PublicFaq items={PURCHASE_FAQ} />
      </PublicSection>

      <section className="public-section">
        <div className="final-cta ag-viewfinder">
          <div className="final-cta-copy">
            <span className="final-cta-eyebrow">準備好了嗎</span>
            <h2 className="final-cta-title">3 步驟結帳，馬上開始健檢你的網站</h2>
            <p className="final-cta-sub">30 秒入帳；不確定要多少點數，先用免費快速檢查看看。</p>
          </div>
          <div className="final-cta-actions">
            <button type="button" className="public-cta public-cta-primary" onClick={() => navigate("/billing")}>
              前往結帳 →
            </button>
            <button type="button" className="public-cta public-cta-ghost" onClick={() => navigate("/free-tools")}>
              免費快速檢查
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

export default PurchasePage;
