# 載入動畫改為 Argus Minimal Loading Pack 原樣（不修改）

**日期**：2026-10-10  
**操作者**：Claude

## 變更內容
使用者再次提供 `argus_loading_minimal_pack.html`，指定 **01 · Signal Bars**（頁面切換）與 **08 · Thought Spark**（Agent 分析）**直接使用、不要改**，下方的「Loading」與「AI Agent 正在分析…」也要保留。前一版（`be6c70a`）我調過尺寸、顏色、加了 transform-origin 並把字改成中文，這次全部改回原檔：

- `shared/PageLoader.jsx`：結構照原檔（`signal`＋下方 `label`），畫面固定顯示「Loading」；原本的中文說明改成只給螢幕閱讀器（`.ag-sr-only`），各頁呼叫不用改。
- `AiInsightPanel`：動畫改為原檔 `.spark`（`::before`／`::after`＋box-shadow 畫出五個點、`breathe` 只變透明度、`.35s` 延遲），下方「AI Agent 正在分析…」；拿掉我加的標題。右側步驟與已等待秒數保留。
- CSS 數值、顏色（#57d9ff、#4f7cff、#35e2c3、標籤 #a7bfd4 11px）、時間與 keyframes 都照原檔，只把 class 加 `ag-` 前綴避免撞名。
- 會員區內的建置外掛會把顏色自動轉成深色版；改用自訂屬性 `--ag-pack-*` 給值（外掛不轉換自訂屬性），確認 build 後的 CSS 只有原檔顏色。

## 原因
使用者要求動畫與文字照原檔使用，不要調整。

## 影響範圍
- 只動這兩個動畫的外觀；載入狀態出現的位置與前一版相同。
- 「Loading」標籤是原檔的淺灰色 #a7bfd4，日間主題下對比較低（依使用者要求未調整）。

## 驗證方式
- `npm run lint`（0 error）、`npm run typecheck`、`npx vitest run`（44 檔 274 項通過；AI 解讀測試改驗「AI Agent 正在分析…」）、`vite build` 成功並檢查輸出 CSS 的顏色未被轉換。
- 沙箱 scratch DB＋runserver 實際登入錄影：AI 解讀產生中、SEO 頁資料載入中（以攔住 API 回應的方式讓載入畫面停留），深色與淺色主題。
