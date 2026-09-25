# 系統健康頁：動態掃描鏈路圖 ＋ 系統資源資訊

**日期**：2026-09-25  
**操作者**：Claude

## 變更內容

### 後端
- 新增 `apps/admin_api/system_metrics.py`：CPU／記憶體／磁碟／網路／運行時間，**純標準庫實作，未新增任何相依套件**。
- `/admin/health/` 回應新增：
  - `chain`：鏈路節點（`database` → `redis` → `celery` → `queue` → `success_rate`）
  - `system`：系統資源
  - 新增 `_probe_database()`（`SELECT 1`）作為鏈路第一節
- 新增 5 項測試（`SystemHealthTests` 共 11 項）。

### 前端
- 新增 `components/admin/AdminScanChain.jsx`：鏈路圖。
- 新增 `components/admin/AdminSystemStats.jsx`：資源卡片。
- 改寫 `AdminHealthPage`：鏈路圖 → 系統資源 → 檢查明細三段式；預設每 15 秒自動更新（可關閉）。
- 新增對應 CSS（含窄螢幕垂直堆疊與 `prefers-reduced-motion`）。

## 參考來源
使用者提供 `/home/jie/Project/argus/monitor`（Flask + psutil 的系統監控頁）作為參考。**採用的是它的資訊設計**（大數字 ＋ 進度條 ＋ 卡片分區 ＋ 即時更新），**未採用它的配色**（該頁是紫藍系 `#4361ee`／`#7209b7`）——依專案 `argus-ui-design` skill，Argus 的識別是 navy × cyan，全部改用 `--admin-*` token 實作，明暗主題皆可用。

## 為什麼不用 psutil（重要）
後端跑在 K8s pod 裡，`psutil.virtual_memory()` 在容器內讀到的是**宿主機**的總記憶體，不是 pod 的 limit。節點 64G、pod 限 1G 時顯示「記憶體 8%」等於沒說，還會讓人誤判資源充足。

因此改為優先讀 **cgroup v2**（`memory.max` / `memory.current` / `cpu.max`），拿不到才退回 `/proc`，並在每個指標上標示 `scope`（`container`／`host`），前端的卡片右上角也顯示「容器」或「主機」。**不標示就是另一種說謊。**

附帶好處：不新增相依套件。

## 鏈路圖的設計理由
原本是四項檢查的平鋪清單，只回答「哪一項壞了」。鏈路圖額外回答「斷在哪一段、後面還有什麼因此跑不動」——節點順序就是掃描實際流經的環節。

連接線的流動動畫**只在前後兩端都正常時播放**；第一個異常節點之後的線全部轉為靜態虛線。這讓「斷點位置」用動態本身表達，不必靠比對一排顏色。`prefers-reduced-motion` 下改以實色＋箭頭表示方向，資訊不流失。

## 刻意的取捨
- **不顯示行程列表**：參考來源有 Top 10 行程，但那是敏感度最高、對 Argus 運維最沒用的資訊，不做。
- **網路只回累計值，速率由前端算**：算速率需兩次取樣，端點沒有穩定的取樣間隔；前端用兩次輪詢的差分計算，只輪詢一次時顯示「量測中…」。
- **自動更新 15 秒**：單次探測約 2.2 秒（Celery ping 1.5s ＋ CPU 取樣 0.15s），15 秒是「有即時感」與「不增加無謂負載」的折衷，且可關閉。
- **CPU 取樣 0.15 秒**：數字會抖動，頁面明說它是瞬時取樣。

## 驗證方式
- `apps.admin_api` 共 **82 項測試全過**（新增 5 項）：鏈路順序必須符合實際管線、DB 檢查存在且 basis 為 `SELECT 1`、`system` 六個區段齊全、CPU／記憶體必須標明 scope、單一指標不可用時回 reason 而非讓端點崩潰。
- `uv run ruff check backend` 全過；`manage.py check` 0 issues。
- 實際呼叫端點：2.23 秒、200，鏈路五節點正確（本機無 worker 故 Worker 為 bad，判定正確）。
- 指標模組單獨實測：0.15 秒，`scope` 正確標示為 `host`（本機無容器限額）。
- `npx vite build` 通過。
- 以 Pillow 模擬明暗兩版版面，確認鏈路斷點在靜態畫面下也可辨識、資源卡片的警示色在兩種底色下皆可讀。
- **待人工確認**：瀏覽器中觀察流動動畫、窄螢幕的垂直堆疊、自動更新與網路速率是否在第二次輪詢後出現。

## 已知未處理
- `AdminMiniChart` / `AdminSparkline` 的座標軸顏色仍寫在 JSX 的 SVG 屬性中（沿用自 S7 的已知缺口），深色下可能偏暗。
