# 拆分 styles.css（14,884 行 → 35 個依序匯入的區塊）

**日期**：2026-09-26
**操作者**：Claude

## 變更內容
- `frontend/src/styles.css` 改為純入口：只依序 `@import` `src/styles/*.css`，並在檔頭註明「順序＝覆寫優先序」。
- 新增 `frontend/src/styles/` 35 個檔，依原檔的區段註解切出**連續**區塊；檔名編號即匯入順序（`0x` 基礎與 token、`1x–2x` 位於 `@layer components` 內、`3x` 登入／響應式／後台補充、`4x` 日間主題、`5x` 評論頁、`6x` 各功能頁、`7x` 首頁與系統健康）。
- 原本位於 `@layer components { … }` 內的區塊（10–23），每檔各自包一層 `@layer components`，Tailwind 會照順序合併輸出。
- `tailwind.config.js`：`content` 補上 `ts,tsx`，排除產生的 `src/shared/apiTypes.ts`。
- 同步文件：`frontend/CLAUDE.md`、`README.md`、`ONBOARDING.md`、`專案導覽.md`、`backend/apps/scans/CLAUDE.md`、`argus-ui-design` skill（`.claude/` 與 `.agents/` 兩份）。

## 原因
單一 14,884 行樣式檔難以定位與協作（前端現代化計畫的一項，使用者同意執行）。

**刻意沒有按網域重新歸類**：日間主題、響應式、後台深色主題等覆寫層靠「出現在後面」才能蓋過同權重規則，把規則搬到元件旁會改變先後順序、靜默翻轉畫面。這次只切不重排，確保零視覺風險；之後若要把覆寫層搬到元件旁，需逐區目視比對。

Tailwind `content` 原本只掃 `js,jsx`：開始導入 TypeScript 後，`.tsx` 元件用到的 class 會被靜默 purge。

## 影響範圍
- 執行期樣式**完全不變**（見驗證）。
- 之後改樣式要改 `src/styles/` 底下的對應檔，不要再往入口 `styles.css` 塞規則；新增整檔時要插在正確的匯入順位。
- 歷史 log 與已註明日期的計畫文件仍寫 `styles.css`，屬歷史紀錄，未修改。

## 驗證方式
- 拆分腳本內建兩項自我檢查：各區塊加上 `@layer` 開關兩行恰好覆蓋原檔每一行一次；依序重組後與原檔字串完全相同。
- 拆分前後 `vite build` 的 `index-*.css` 與 `vendor-reactflow-*.css` 以 `cmp` 比對：**逐位元組相同**（content hash 同為 `index-DvJ2Sx5a`）。
- Tailwind `content` 修正：臨時放一個含 `tracking-[0.371em]` 的 `.tsx`，修正後輸出含該規則、改回舊設定則不含；移除臨時檔後輸出仍與基準逐位元組相同。
- `npm run typecheck` 無錯誤、`npm test` 14 passed、`vite build` 成功。
