# 採用 argus_report module：前置準備（相依、字型、vendor、資產路徑）

**日期**：2026-09-01
**操作者**：Claude
**觸發**：使用者提供 `argus_report_module/`（含 `argus-report-SAMPLE.docx` 範本），指出 scan 43 的產出與預期落差仍大。

## 為什麼先做前置

module 的圖表全由 matplotlib 繪製，**缺 CJK 字型時是直接 `FileNotFoundError` crash**（我親自撞到，不是推測）。字型那關沒過的話，後面的整合全部白做，所以先把「容器裡真的產得出中文圖表」證明出來再往下走。

## 審查結論（先於實作）

實測驗證這套 module 可以採用：

- 用 `example_input.json` 重跑，得到 186 段 / 8 表 / 5 圖 / 6563 字元，**與 `argus-report-SAMPLE.docx` 完全一致**——範本就是它的產出。
- `example_input.json` 就是我們 scan 43 的資料（`report_id: ARGUS-43-20260901-D009`、NTUB、16 項發現），代表「我們的資料 → 它的 schema」這條映射已被人工證明可行。
- 936 行、純本地運算、無對外連線、無外部程序。
- schema 幾乎與現有邏輯 1:1：去重分組、分數、前次比較、術語表、技術索引、per-rule 文案、PII 遮罩、報告編號、授權聲明全部是它要的輸入。**這套 module 取代的只是排版層。**

與現況的差距（scan 43 vs 範本）：圖表 1 vs **5**、字元 **14466 vs 6563**（我們是 2.2 倍）。它有而我們沒有的：分數環圈、分類長條、嚴重度分佈、趨勢線、一頁摘要、發現項目依嚴重度分組。

## 變更內容

### 1. 相依：`uv add matplotlib`
連帶 numpy、fonttools、kiwisolver、cycler、pyparsing。

### 2. Dockerfile 安裝 `fonts-noto-cjk`
backend 容器原本**沒有任何 CJK 字型**（`fc-list | grep -c cjk` = 0）。

### 3. Vendor module 至 `backend/apps/scans/report_render/`
**必須在 `backend/` 之內**——`COPY backend ./backend` 不含 `frontend/`。內部 import 全是相對路徑，原樣搬移即可運作。一併 vendor `schema.json`（下一階段要用來驗證 payload）。

`pyproject.toml` 的 ruff `extend-exclude` 加入該目錄：為了過 lint 去重排第三方程式碼，日後更新 module 會變成逐行手動合併。

### 4. 修 `theme.py` 的字型解析（唯一的在地修改）
原版把路徑寫死並註明「override via env if needed」，但**實作裡沒有讀任何環境變數**——module 自身的文件漂移。改為：環境變數 `ARGUS_REPORT_FONT_REGULAR` / `_BOLD` → 三組候選路徑 → 都找不到時 `RuntimeError` 並附上可執行的修法。

**刻意保留「大聲失敗」**：退回預設字型的話圖表中文會變成一整排 □，報告照樣產出、照樣寄給客戶，沒有人會發現。

### 5. 修 Codex 那批的品牌 PNG 路徑（同根因）
`reports.py` 原本讀 `PROJECT_ROOT/frontend/public/*.png`，而 backend image 裡沒有 `frontend/`。我進容器實測確認 `/app/` 只有 `.venv`、`backend`、`pyproject.toml`、`uv.lock`。加上 `if exists()` 保護，**它會靜默退回純文字——不報錯、測試全過、但正式站的報告永遠沒有藝術字**。

三張 PNG 移至 `backend/apps/scans/report_assets/`，路徑改為 `Path(__file__).parent / "report_assets"`。前端完全沒有引用這些圖（grep 確認），故移除 `frontend/public/` 的重複副本——留著會造成「改一份忘另一份」的漂移，而那正是本次 bug 的成因。

## 驗證方式

- `uv run ruff check backend` → All checks passed
- `uv run python backend/manage.py test apps` → **Ran 779 tests，OK（skipped=1）**（無回歸）
- **容器內端到端實測**（這是本階段的重點）：
  - `docker compose build web` → 成功
  - 容器內字型存在、matplotlib 3.11.1 / numpy 2.5.2 就緒、`theme.py` 解析到 `/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`
  - 在容器內用 `example_input.json` 產出 772KB 報告，內嵌 5 張圖
  - **把圖表拉出來逐張目視**：分類長條圖與分數環圈的中文完整渲染、**零 □**，配色依分數分級正確切換，60/80 門檻虛線正常

## 過程中發現的環境問題

**本機磁碟 100% 滿**（61G 用掉 59G，可用 0），導致 `docker build` 的 `apt-get update` 出現 `invalid signature` 而失敗——簽章錯誤只是症狀。已清除 docker build cache（2.98GB，純快取、可重建）解除阻塞，目前 98%、剩 1.6G。**這仍然很緊，需要你處理**（`docker system df` 顯示還有 6.1GB 可回收的 image）。

## 未處理／待決事項

- **下一階段才是主體**：把 `reports.py` 的排版程式碼（約 700 行）換成 `build_report_payload(scan_job) -> dict`，接到 `report_render.generate_report()`。既有的分數、去重、排序、PII 遮罩、防偽、快取邏輯與測試全部保留。
- **`argus_report_module/` 目前未納入版控**（2.2MB，含範本與範例資料）。要不要進 repo 需使用者決定；`schema.json` 已 vendor 進 `report_render/`。
- **本機磁碟仍在 98%**。
- 舊的 `reports.py` 排版程式碼在下一階段替換前仍在使用中。
