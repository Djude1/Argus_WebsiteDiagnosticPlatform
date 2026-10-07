# 系統手冊第 3 章核對

## 已核對的事實（2026-10-07）

- 掃描維度為 SEO、AEO、GEO、UX、資安；來源：`backend/apps/scans/models.py` 的 `ALL_CATEGORIES` 與 `Finding.Category`。
- `SiteProject` 關聯歷次 `ScanJob`；`Page` 與 `Finding` 均關聯 `ScanJob`，`Finding.page` 可為空，站台級問題應與頁面級問題一併判讀。
- 報告下載使用 `backend/apps/scans/views.py::ensure_report_file`：有效快取直接沿用，需要時才重新產生。`reports.py::build_scan_report` 先在暫存目錄以 python-docx 排版，再由 LibreOffice 轉成 PDF；SHA-256 與防偽紀錄針對 PDF，DOCX 是中間產物。
- MCP 工具共用掃描 serializer、派工、取消、估價與報告服務，並非另外建立扣點流程；來源：`backend/apps/mcp_access/tools.py` 與 `views.py`。
- Search Console 以 `webmasters.readonly` 讀取資源、搜尋成效與網址索引狀態；網域驗證只採認涵蓋目標的擁有者權限。來源：`backend/apps/scans/seo/gsc.py`、`domain_verification.py`。
- `pyproject.toml` 要求 Python >=3.12；本機資料庫預設 SQLite，Compose 與 K8s 設定使用 PostgreSQL 16、Redis 7。
- 目前 `frontend/package-lock.json` 的 jsdom 30.1.1 要求 Node `^22.22.2 || ^24.15.0 || >=26.0.0`。Windows 建置依專案規則使用 Node 22 helper；可建置與可執行完整測試應分別驗證，不能由建置成功推論測試成功。
- `frontend/Dockerfile` 的建置階段仍使用 Node 20；不能把平台所有建置環境統稱為 Node 22。依賴更新後需重新核對鎖定檔及 engine。
- OpenAPI schema 離線產生，供部分前端 API 型別使用，沒有公開 schema 端點；來源：`backend/config/settings.py`、`frontend/src/shared/apiTypes.ts`。

## 文件修訂邊界

- 本次交付第 3 章文字與兩張表格的替換建議，沒有直接修改線上 Word 或系統程式碼。
- 架構圖核心資料流可保留；「下載時產生」應補充快取行為。若圖名宣稱涵蓋外部整合，再補 MCP 用戶端、Search Console 與綠界。
- 使用者未提供第 10 章測試紀錄及完整參考文獻，不能認定 Node 22.17 的建置敘述或文獻編號已驗證。
- UML 的 boundary、control、entity 是分析角色，不應被描述成必然與每個實作類別一對一對應。
