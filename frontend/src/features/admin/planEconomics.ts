// 購點方案的成本與毛利試算（後台定價參考用）。
//
// ⚠ 2026-09-26 修正：原本把每 coin 成本當成每頁成本（NT$0.67／coin），沿用了
//   「1 coin = 1 頁」的舊假設；但後端實際是每頁 10 coin（五維全選＝5 維 × ARGUS_COIN_PER_CATEGORY），
//   成本因此高估 10 倍——種子方案的毛利實際約 90%，後台卻顯示 2%～33% 並標成
//   「須重新定價」。現在以「頁」為成本單位，coin → 頁的換算用後端提供的 coin_per_page。
//
// 掃描按維度計費後，使用者只勾部分維度時一頁更便宜、同樣 coin 能掃更多頁；
// 這裡一律以「五維全選」估算，是保守（成本最高）的算法。

/**
 * 每掃描一頁的內部成本（NT$）。推算見 log/2026-06-14_ui-ux-billing-cms-audit.md：
 *   - MiniMax M2 token 成本：每 12 頁 scan ≈ NT$0.43
 *   - 伺服器月固定費攤提（200 scans/月）：每 scan ≈ NT$7.5
 *   - 合計每 scan ≈ NT$8 → 每頁 ≈ NT$0.67
 *
 * ⚠ 待決定（稽核 Q2）：這是營運估算，是否改由後端設定提供尚未定案，暫時保留在前端。
 */
export const COST_PER_PAGE_NTD = 0.67;

export type PlanEconomics = {
  /** 內部成本（NT$，四捨五入到 0.1） */
  cost: number;
  margin: number;
  /** 毛利率（%，四捨五入到整數；售價為 0 時為 0） */
  marginPct: number;
  /** 這些 coin 約可掃幾頁 */
  pagesEstimate: number;
  tone: "good" | "warn" | "bad";
  toneLabel: "健康" | "偏低" | "須重新定價";
};

export function planEconomics(
  plan: { price_ntd?: number; coin_amount?: number },
  coinPerPage: number,
): PlanEconomics {
  const coin = plan.coin_amount || 0;
  const price = plan.price_ntd || 0;
  const pages = coinPerPage > 0 ? coin / coinPerPage : 0;
  const cost = Number((pages * COST_PER_PAGE_NTD).toFixed(1));
  const margin = Number((price - cost).toFixed(1));
  const marginPct = price > 0 ? Math.round((margin / price) * 100) : 0;
  const tone = marginPct >= 80 ? "good" : marginPct >= 50 ? "warn" : "bad";
  return {
    cost,
    margin,
    marginPct,
    pagesEstimate: Math.floor(pages),
    tone,
    toneLabel: tone === "good" ? "健康" : tone === "warn" ? "偏低" : "須重新定價",
  };
}
