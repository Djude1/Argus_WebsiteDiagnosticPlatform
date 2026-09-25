# 後台 UI 重構 S3：概覽改建為待辦中心

**日期**：2026-09-25  
**操作者**：Claude

## 變更內容

### 後端
- `apps/admin_api/views.py`：`overview` 回應新增 `triage` 區塊，含 `scans_stuck`、`scans_stuck_threshold_min`、`scans_stuck_oldest_at`、`scans_failed_today`、`scans_in_progress`、`reviews_pending`、`reports_pending`、`scans_today`。
- 新增常數 `STUCK_SCAN_THRESHOLD_MINUTES = 10` 與 `IN_PROGRESS_SCAN_STATUSES`。
- 新增 `TriageTests` 5 項（含前端欄位契約測試）。

### 前端
- 新增 `features/admin/AdminOverviewPage.jsx`：待辦中心，資訊順序為 ① 待辦 ② 今日脈搏 ③ 14 天趨勢 ④ 總量統計 ⑤ 成本與明細。
- 四張待辦卡片皆為可點按鈕，帶篩選參數跳轉：排隊逾時 → `/admin/scans?status=queued`、今日失敗 → `/admin/scans?status=failed`、待審檢舉 → `/admin/reviews?filter=reported`、待回覆評論 → `/admin/reviews?filter=pending`。
- 全部為 0 時顯示正向空狀態（綠色、勾號），而非灰色的「無資料」。
- 從 `AdminPages.jsx` 抽出 `components/admin/AdminStatCard.jsx`（含 `AdminSparkline`）與 `components/admin/AdminMiniChart.jsx`。

## 原因
規劃 §4-1：原「概覽」是六張總量統計卡 ＋ 趨勢圖 ＋ 用量分佈，全部是「已經發生的事」，沒有任何元素回答「現在該處理什麼」。待回覆評論與待審檢舉有數字卻點不進去；卡住的掃描完全看不到，而那是本平台最關鍵的運維風險（Redis／Celery worker／Playwright 任一環節斷掉就會整批卡住）。

**為何不新增探測端點**：依規劃 §7 Q1 的暫定假設，真正判斷 Celery worker 死活需要探測 broker，屬於另一層級的工作。這裡以 `ScanJob` 停留在 `queued` 的時間差近似（門檻 10 分鐘），足以讓管理員注意到異常並進一步查。此近似已寫入程式註解。

**統計卡降級而非刪除**：累計營收、使用者總數等仍有價值，只是不是每日決策依據，因此移到趨勢圖之後；原本的 `hero` 放大樣式取消。

## 影響範圍
- `/admin/overview` 的版面與資訊順序大幅改變；資料來源仍是既有的 `overview` 與 `dashboard` 兩個端點。
- `AdminPages.jsx` 由 2604 行降至 2287 行；產出 chunk 由 70.11 kB 降至 62.46 kB，新增 `AdminOverviewPage` 獨立 chunk（11.96 kB）。
- 待辦卡片的跳轉依賴 S2 的網址篩選；兩者相依，缺一不可。

## 驗證方式
- 後端：`apps.admin_api` 共 60 項測試全過（新增 5 項）；`uv run ruff check backend` 全過；`manage.py check` 0 issues。
- 契約測試鎖住前端用到的 8 個 triage 欄位——少一個不會噴錯，只會靜靜顯示 undefined。
- 前端：`npx vite build` 通過（13.19s）。
- 以 Pillow 模擬版面確認：有待辦的卡片上色（紅／琥珀）、數字為 0 的保持中性不搶注意力。
- **待人工確認**：瀏覽器中點擊各待辦卡片是否正確落在已篩選的列表；`prefers-reduced-motion` 下 hover 位移是否已停用。

## 未做
- S4 掃描處置（取消／重排／退點）仍待 Q6 計費決策。
- 系統健康頁仍待 Q1。
- `COIN_COST_NTD` 搬遷仍待 Q2。
