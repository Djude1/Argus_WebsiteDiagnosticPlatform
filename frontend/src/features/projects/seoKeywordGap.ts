// 目標關鍵字 × Search Console 落差分析（roadmap §1 SEO 第 4 項）。
// 只用頁面已有的資料：keyword_report（後端 seo/keywords.py，頁面內容比對）與 gsc/performance 的
// 查詢字詞（前 200 個，依點擊排序）。純函式，不呼叫 API。

/** gsc.performance() 的 queries 列（backend/apps/scans/seo/gsc.py）。 */
export type GscQuery = {
  query: string;
  clicks: number;
  impressions: number;
  position: number;
  page: string;
};

/** keyword_report 列（backend/apps/scans/seo/keywords.py）。 */
export type KeywordReportRow = {
  keyword: string;
  best_page: { url: string } | null;
};

export type RankBand = "first" | "second" | "beyond";

export type KeywordGap =
  | { keyword: string; status: "none"; advice: string }
  | {
      keyword: string;
      status: RankBand;
      queries: number;
      impressions: number;
      clicks: number;
      bestPosition: number;
      bestQuery: string;
      landingPage: string;
      landingMismatch: string;
      advice: string;
    };

const WS = /[\s\u3000]+/g;

function norm(text: string | null | undefined): string {
  return String(text || "").replace(WS, " ").trim().toLowerCase();
}

function sameUrl(a: string, b: string): boolean {
  const key = (url: string) => (url.split("#")[0] || "").replace(/\/+$/, "").toLowerCase();
  return Boolean(a && b) && key(a) === key(b);
}

// 平均排名分段：第 1 頁（≤10）最值得維持，第 2 頁（11–20）最有機會推進
function rankBand(position: number): RankBand {
  if (position <= 10) return "first";
  if (position <= 20) return "second";
  return "beyond";
}

const BAND_ADVICE: Record<RankBand, string> = {
  first: "",
  second: "排在第 2 頁附近，加強相關頁面的標題與內容最有機會進到第 1 頁。",
  beyond: "已有曝光但排名較後，可建立或加強以這個主題為主的頁面。",
};

/** 每個目標關鍵字：相關搜尋詞（字詞包含關鍵字）的曝光、點擊、最佳排名、Google 帶到的頁面與建議。 */
export function keywordGap(
  keywordReport: KeywordReportRow[],
  queries: GscQuery[] | null | undefined,
): KeywordGap[] {
  return keywordReport.map((row): KeywordGap => {
    const needle = norm(row.keyword);
    const matches = (queries || []).filter((q) => norm(q.query).includes(needle));
    const [first, ...rest] = matches;
    if (!first) {
      return {
        keyword: row.keyword,
        status: "none",
        advice: row.best_page
          ? "頁面有提到，但期間內沒有相關搜尋曝光；確認頁面已被收錄，並把關鍵字放進 Title 與 H1。"
          : "期間內沒有相關搜尋曝光，也沒有頁面提到；若是重要主題，建立專門的頁面。",
      };
    }
    const best = rest.reduce((a, b) => (b.position < a.position ? b : a), first);
    const top = rest.reduce((a, b) => (b.impressions > a.impressions ? b : a), first);
    const band = rankBand(best.position);
    const landingMismatch =
      row.best_page && top.page && !sameUrl(top.page, row.best_page.url) ? top.page : "";
    const advice = [
      BAND_ADVICE[band],
      landingMismatch
        ? "Google 帶訪客去的頁面和你內容最相關的頁面不同；確認哪一頁才是這個主題的主頁，"
          + "並從其他頁面連結過去。"
        : "",
    ].join("");
    return {
      keyword: row.keyword,
      status: band,
      queries: matches.length,
      impressions: matches.reduce((sum, q) => sum + q.impressions, 0),
      clicks: matches.reduce((sum, q) => sum + q.clicks, 0),
      bestPosition: best.position,
      bestQuery: best.query,
      landingPage: top.page || "",
      landingMismatch,
      advice,
    };
  });
}

/** 有曝光但不包含任何目標關鍵字的搜尋詞（依曝光排序），可考慮設為目標。 */
export function untargetedQueries(
  keywords: string[],
  queries: GscQuery[] | null | undefined,
  limit = 10,
): GscQuery[] {
  const needles = keywords.map(norm).filter(Boolean);
  return (queries || [])
    .filter((q) => q.impressions > 0)
    .filter((q) => {
      const query = norm(q.query);
      return !needles.some((needle) => query.includes(needle) || needle.includes(query));
    })
    .sort((a, b) => b.impressions - a.impressions || a.position - b.position)
    .slice(0, limit);
}
