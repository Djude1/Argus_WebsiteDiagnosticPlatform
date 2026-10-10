# 載入動畫：頁面切換用 Signal Bars、AI 解讀用 Thought Spark

**日期**：2026-10-10  
**操作者**：Claude

## 變更內容
使用者提供「ARGUS Minimal Loading Pack」，選定頁面切換用 **01 · Signal Bars**、AI 分析用 **08 · Thought Spark**，並請我另外加幾款設計：

1. **頁面切換／頁面載入（Signal Bars）**：新增 `shared/PageLoader.jsx`（五根細長條依序起伏＋一行說明，`role="status"`）。
   - `App.jsx` 換頁的 `Suspense` fallback 改用它。
   - 會員區各頁 `if (!data)` 的「載入…中…」純文字（SEO、總覽、問題分析、頁面、資安、專案清單／工作區、掃描詳情子頁、頁面優化成果頁，共 22 處）、帳號設定頁、方案頁的方案載入都改用它。
   - 樣式：會員區外在 `05-brand.css`（`--ag-primary`→`--ag-info` 漸層，深淺主題自動）；會員區內在 `legacy-member/92-layout.css`（舊版範圍會重置外部規則，所以另給一份）。
2. **AI 解讀（Thought Spark）**：`AiInsightPanel` 的載入動畫由「守望之眼」改為五個光點分兩排依序呼吸閃爍（`AiThinkingLoader`，`.ai-spark`）；步驟與已等待秒數保留。刪除守望之眼的 SVG 與樣式。
3. **新設計（只在比較頁，未做進網站）**：13 Watch Iris、14 Evidence Scan、15 Crawl Trail、16 Radar Sweep，連同 01、08 放在比較頁給使用者挑。
4. 偏好減少動態時以上動畫全部靜止。

## 原因
使用者指定喜歡的兩款動畫，並希望看到更多同風格的選項。

## 影響範圍
- 只動前端呈現；沒有 API 或資料變更。
- 原本「載入中…」純文字的地方改為動畫＋同一句文字，對螢幕閱讀器一樣宣告為載入中。
- 文件：`frontend/CLAUDE.md`（PageLoader 規則、AI 解讀動畫名稱）、`docs/scan-stage-checks.md`、需求書內容與修訂提示詞 R11 的動畫描述改為「思考光點」。

## 驗證方式
- `npm run lint`（0 error）、`npm run typecheck`、`npx vitest run`（44 檔通過；新增 `PageLoader.test.tsx`；SEO 頁測試改以提示文字找 Search Console 錯誤提示，因為載入動畫也是 `role="status"`）；`vite build` 成功。
- 沙箱 scratch DB＋runserver 實際登入錄影：報告頁 AI 解讀產生中（Thought Spark）、SEO 頁延遲 API 時的 Signal Bars，深色與淺色主題。
