import { useEffect } from "react";

// 每個網址各自的 <title>、meta description 與 canonical（2026-10-12）：SPA 只有一份 index.html，
// 原本所有頁面同一個標題與摘要、也沒有 canonical（Argus 自掃 4.12、4.17、4.22）。
// 爬蟲讀的是執行 JavaScript 後的頁面，所以在前端設定就會生效。

export const SITE_NAME = "Argus AI網站健檢平台";

// 與 index.html 的 meta description 相同；50–160 字（Argus SEO 規則）
export const DEFAULT_DESCRIPTION =
  "Argus AI網站健檢平台一次檢查網站的 SEO、AEO、GEO、使用體驗與資訊安全，每項問題附證據、修正建議與可查驗的 PDF 報告。";

// 公開頁各自的搜尋摘要；會員頁不會被搜尋引擎收錄，沿用預設
const DESCRIPTIONS: [RegExp, string][] = [
  [/^\/(project\/?)?$/, DEFAULT_DESCRIPTION],
  [/^\/free-tools\/?$/, "免費使用 Argus 的單頁網站健檢、網站測速與釣魚網址、釣魚郵件偵測，不必註冊，輸入網址即可看到分數、問題清單與改善建議。"],
  [/^\/purchase\/?$/, "Argus 的方案與計費方式：首次完整掃描免費，之後依掃描頁數與面向扣點，掃描失敗或取消全額退回，另有每月訂閱與點數包可選。"],
  [/^\/download\/?$/, "把 Argus AI網站健檢平台安裝到電腦或手機桌面：支援 Chrome、Edge 與 iPhone Safari，一鍵安裝後可像應用程式一樣開啟與查看掃描結果。"],
  [/^\/verify(\/[^/]+)?\/?$/, "輸入 Argus 報告編號，即可確認報告是否由 Argus 出具，並查看掃描目標、掃描與報告產生時間、整體分數與 PDF 的 SHA-256 指紋，不需要登入。"],
  [/^\/partners\/?$/, "與 Argus 洽談商業合作：網站開發與數位代理、維運與技術服務、平台與技術合作，可用 Argus 健檢報告作為交付與驗收依據，填寫表單即可聯繫。"],
  [/^\/privacy\/?$/, "Argus AI網站健檢平台的隱私權政策：說明我們收集哪些資料、如何使用與保存、Google Search Console 授權的範圍，以及如何刪除帳號與資料。"],
  [/^\/terms\/?$/, "Argus AI網站健檢平台的服務條款：說明掃描授權、使用限制、點數與付款、報告的使用範圍與免責事項，使用服務前請先閱讀。"],
  [/^\/scanner\/?$/, "寫給網站管理者：Argus 掃描器的 User-Agent、出口 IP、被動與主動檢查各會做什麼與請求速率，以及如何在 robots.txt 或 WAF 封鎖或放行。"],
  [/^\/reviews\/?$/, "看看其他使用者對 Argus AI網站健檢平台的評價與心得，評論只開放給完成過掃描的使用者，並可依星等篩選與查看官方回覆。"],
  [/^\/login\/?$/, "登入或註冊 Argus AI網站健檢平台，建立網站專案後即可掃描網站的 SEO、AEO、GEO、使用體驗與資安問題，並下載 PDF 報告。"],
];

// 依序比對，第一個符合的生效；動態網址段用 [^/]+
const TITLES: [RegExp, string][] = [
  [/^\/(project\/?)?$/, "SEO、AEO、GEO、資安與使用體驗一次健檢"],
  [/^\/free-tools\/?$/, "免費網站快速檢查：單頁健檢、測速、釣魚網址偵測"],
  [/^\/purchase\/?$/, "方案與計費"],
  [/^\/download\/?$/, "下載與安裝"],
  [/^\/verify(\/[^/]+)?\/?$/, "報告查驗"],
  [/^\/partners\/?$/, "商業合作"],
  [/^\/privacy\/?$/, "隱私權政策"],
  [/^\/terms\/?$/, "服務條款"],
  [/^\/scanner\/?$/, "掃描來源說明"],
  [/^\/reviews\/?$/, "使用者評論"],
  [/^\/login\/?$/, "登入／註冊"],
  [/^\/password-reset(\/confirm)?\/?$/, "重設密碼"],
  [/^\/account\/setup\/?$/, "完成帳號設定"],
  [/^\/projects\/?$/, "所有網站專案"],
  [/^\/projects\/new\/?$/, "新增網站專案"],
  [/^\/projects\/[^/]+\/scans\/?$/, "掃描與報告"],
  [/^\/projects\/[^/]+\/seo\/?$/, "SEO 分析"],
  [/^\/projects\/[^/]+\/security\/?$/, "資安分析"],
  [/^\/projects\/[^/]+\/issues\/?$/, "問題分析"],
  [/^\/projects\/[^/]+\/pages\/?$/, "頁面"],
  [/^\/projects\/[^/]+\/aeo\/?$/, "AEO 問答"],
  [/^\/projects\/[^/]+\/settings\/?$/, "專案設定"],
  [/^\/projects\/[^/]+\/?$/, "專案總覽"],
  [/^\/scans\/[^/]+\/rebuild\/[^/]+\/?$/, "頁面優化成果"],
  [/^\/scans\/[^/]+\/strengths\/?$/, "網站優勢"],
  [/^\/scans\/[^/]+\/architecture\/?$/, "架構與信任"],
  [/^\/scans\/[^/]+\/topology\/?$/, "網站拓撲"],
  [/^\/scans\/[^/]+\/performance\/?$/, "效能"],
  [/^\/scans\/[^/]+\/score\/?$/, "分數說明"],
  [/^\/scans\/[^/]+\/?$/, "掃描報告"],
  [/^\/optimized\/[^/]+\/?$/, "頁面優化成果"],
  [/^\/domains\/?$/, "網域驗證"],
  [/^\/billing\/?$/, "購點與訂閱"],
  [/^\/settings\/?$/, "帳號設定"],
  [/^\/mcp\/?$/, "MCP 接入"],
  [/^\/admin(\/|$)/, "管理後台"],
];

export function titleForPath(pathname: string): string {
  const match = TITLES.find(([pattern]) => pattern.test(pathname));
  return match ? `${match[1]}｜${SITE_NAME}` : SITE_NAME;
}

export function descriptionForPath(pathname: string): string {
  return DESCRIPTIONS.find(([pattern]) => pattern.test(pathname))?.[1] ?? DEFAULT_DESCRIPTION;
}

function upsertHead(selector: string, create: () => HTMLElement, attr: string, value: string) {
  let el = document.head.querySelector(selector);
  if (!el) {
    el = create();
    document.head.appendChild(el);
  }
  el.setAttribute(attr, value);
}

export function useDocumentTitle(pathname: string): void {
  useEffect(() => {
    document.title = titleForPath(pathname);
    upsertHead('meta[name="description"]', () => {
      const meta = document.createElement("meta");
      meta.setAttribute("name", "description");
      return meta;
    }, "content", descriptionForPath(pathname));
    // canonical 指向目前網址本身（不含查詢字串）；網站有多個網域時各自指向自己
    upsertHead('link[rel="canonical"]', () => {
      const link = document.createElement("link");
      link.setAttribute("rel", "canonical");
      return link;
    }, "href", `${window.location.origin}${pathname}`);
  }, [pathname]);
}
