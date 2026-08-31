# 掃描報告品質改善 第四階段（上）：報告防偽、免責聲明與快取

**日期**：2026-08-31
**操作者**：Claude
**依據**：[`docs/scan-report-quality-audit-2026-08-30.md`](../docs/scan-report-quality-audit-2026-08-30.md) 第四階段的 E1-E4 與 G1

## 變更內容

### 1. 新增 `ReportVerification` model（`backend/apps/scans/models.py` + migration `0011`）
`scan_job`（OneToOne）／`report_number`（unique）／`content_sha256`／`generated_at`。

### 2. 報告編號（E2）
`reports.py::build_report_number()`：`ARGUS-{掃描編號}-{日期}-{4 碼驗證碼}`，驗證碼為 `HMAC(SECRET_KEY, "argus-report:{pk}")` 前 4 碼。

- **不含時間戳，所以重新產生時編號不變**。報告一旦交付就可能被轉寄存檔，換編號會讓已流出的副本失效。
- 用 SECRET_KEY 做 HMAC 是為了讓編號無法被憑空捏造出「看起來合理」的值；只取 4 碼是因為它防的是隨手偽造，真正的比對靠查驗端點與內容雜湊。

編號印在**封面**與**每一頁頁尾**。

### 3. 內容指紋與公開查驗端點（E3）
- 存檔後計算 `.docx` 的 SHA-256 寫入 `ReportVerification`。
- **報告本身只印編號、不印雜湊**——雜湊要涵蓋整份檔案，檔案裡又要有雜湊，會循環相依。雜湊由查驗頁提供，收件者自行 `sha256sum` 比對。
- `GET /api/verify/<report_number>/`（`verify_views.py`，`AllowAny` + `AnonRateThrottle`）。回應只有：編號、目標網址、掃描與產生時間、整體分數、內容雜湊。
- **絕不回傳掃描發起人**，否則用報告編號就能反查使用者身分。有專屬測試鎖定。

### 4. 前端查驗頁（E3）
`frontend/src/features/public/PublicPages.jsx::VerifyReportPage`，路由 `/verify` 與 `/verify/:reportNumber`。

- 收件者多半不是 Argus 使用者，所以**不需登入**；網址帶編號直接查，沒帶就給輸入框。
- 成功／查無兩種狀態各有明確視覺區隔，並說明「查驗能證明什麼」。
- 入口放在**頁尾**而非主導覽：主導覽已有 6 項，接近 skill 訂的 5–7 上限，而查驗的主要入口是報告封面上的指引，不是站內瀏覽動線。
- 樣式寫進 `styles.css`（`@layer components` 內，比照既有 `insight-*` 卡片），含日間模式覆寫與窄螢幕單欄；無 inline style。

### 5. 免責聲明（E4）
附錄新增「5.4 免責聲明」：本報告僅反映掃描當下從外部可觀測的特徵，不等同完整滲透測試或原始碼稽核，未列出的項目不代表不存在風險。

### 6. 封面 logo：有就用、沒有就用字標（E1）
偵測 `frontend/public/argus-logo.png`，存在才 `add_picture`，否則維持既有 ARGUS 字標。**刻意不引入 SVG 轉檔套件**——`cairosvg` 有系統函式庫相依，會拖累 CI 與 Docker build；用 Pillow 手繪漸層星形則會失真。把 PNG 放進該路徑即自動生效。

### 7. 報告快取（G1）
`views.py` 的 report action 不再每次重跑產生器。**這不只是效能問題**：重新產生會改變內容雜湊，讓已交付出去的副本在查驗頁對不上。必須「檔案存在 **且** 有防偽紀錄」才視為可重用——舊版留在磁碟上、沒有編號的報告要重新產生。

`reports.py` 匯出 `report_output_path()`，避免 views.py 重複一份檔名慣例。

### 8. 新增 `backend/apps/scans/tests_report_verification.py`（10 項）
防偽紀錄寫入、編號跨重產不變、編號出現在封面與頁尾、雜湊與檔案相符、免責聲明、查驗端點回傳內容、**查驗端點不得洩漏使用者**、未知編號 404、快取不重產、檔案被刪仍可重產。

### 9. 文件同步
- `backend/apps/scans/CLAUDE.md`：新增「報告防偽與快取」章節。
- `.claude/skills/argus-ui-design/SKILL.md`：**修正過時的架構描述**。原文寫「`App.jsx` 是 6500+ 行單檔、禁止新增獨立 `.jsx` 元件檔」，實際上 `App.jsx` 只有 172 行、頁面早已依 domain 拆進 `src/features/`，而 `frontend/CLAUDE.md` 明載「鼓勵依 domain 新增獨立 `.jsx` 元件檔」——skill 與硬限制文件互相矛盾且與程式碼不符。

## 驗證方式

- `uv run ruff check backend` → All checks passed
- `uv run python backend/manage.py check` → no issues
- `uv run python backend/manage.py test apps` → **Ran 738 tests，OK（skipped=1）**（前次 728，+10 新測試，無回歸）
- **快取測試有效性反證**：`git stash` 掉 views.py 的快取後重跑，`test_second_download_does_not_regenerate_the_report` 確實失敗。
  - 順帶記錄：這個測試最初寫成「比對前後兩次的內容指紋」，在尚未實作快取時**僥倖通過**（兩次下載落在同一秒，報告裡的產生時間字串相同）。已改為斷言「產生器被呼叫幾次」，變成確定性測試。
- **端到端實跑**：產生報告 → 檔案 SHA-256 與 DB 紀錄相符（True）→ 未登入呼叫 `/api/verify/<編號>/` 回 200 且六個欄位正確 → 未知編號回 404 → 回應不含使用者名稱。
- **前端 build 通過**（`✓ built in 12.36s`）。

### 關於前端 build 指令

CLAUDE.md 規定 build 一律用 `frontend/build-node22.ps1`、禁止 `npm run build`，成因是「Node v24 + Rollup 4.x **在 Windows** 會 STATUS_STACK_BUFFER_OVERRUN」。該 ps1 的實際內容只是「找到 portable Node 22 → 加進 PATH → 執行 `npm run build`」，且是 PowerShell + `D:\` 路徑，在 Linux 無法執行。

本機是 **Linux + Node v22.23.1**，禁令的兩個成因（Node 24、Windows）都不成立，且 `frontend/dist` 已 gitignore（由 CI 建置）。因此以「驗證 JSX 可編譯」為目的執行了等效的 `npm run build`。**這個規則目前沒有 Linux 對應寫法，值得補進文件**（本次未改，因為它涉及團隊共用規則的適用範圍，應由使用者決定）。

## 未處理／待決事項

- **仍未做視覺驗證**：本機沒有 LibreOffice / pandoc，`.docx` 的字型、行距、表格寬度、分頁落點未經確認；查驗頁也只有 build 通過，**沒有實際在瀏覽器開過**。
- **`frontend/public/argus-logo.png` 尚未存在**，目前封面用字標。要放圖的話從 `favicon.svg` 匯出 256×256 PNG 放進該路徑即可。
- 第四階段剩餘：F4 頁面清單、F5 截圖、F6 bounding_box / selector、F7 與前次掃描比較、G2 報告檔案保留期限與清理。
- **舊報告沒有防偽紀錄**：`ReportVerification` 從本次開始寫入，既有掃描要重新下載一次才會產生編號。
- 「0 個 finding = 100 分」與 worker rollout 砍掉進行中掃描這兩項仍未處理。
