# 網域所有權驗證（主動測試閘門）——複賽評審問題 1 核心回應

- **日期**：2026-09-19
- **操作者**：ZCode（subagent 實作，main 驗收）

## 變更內容

- 新檔 `backend/apps/scans/domain_verification.py`：驗證引擎——`generate_token()`（secrets 32 hex）、`normalize_domain()`（拒 IP/localhost/非 FQDN）、`verify_dns_txt()`（`_argus-verification.<domain>` TXT→整組重試 3 次×5s）、`verify_meta_tag()`（首頁前 64KB 需同時含標籤名＋token）、`verify_html_file()`（`/.well-known/argus-verification.txt` 全等比對）、`run_verification()`（成功→verified＋90 天效期＋記錄方法；失敗→last_error）。HTTP 抓取一律先過 `assert_public_http_url` SSRF 檢查＋串流限量（64KB/5MB）
- `backend/apps/scans/models.py`：新 `VerifiedDomain`（status/method/token/expires_at/admin_override 等；`is_effectively_verified`＝override 或 verified 未過期）；`ScanJob.clean()` 加網域閘門（與既有 active_testing_authorized 並存）
- `backend/apps/scans/services.py`：`registrable_domain()`＋`user_owns_domain()`（父網域候選比對，子網域涵蓋，避免 eTLD+1 依賴）
- `backend/apps/scans/serializers.py`＋`views.py`＋`urls.py`：`/api/scans/domains/` ViewSet（list/create〔回 token＋三方法 instructions〕/verify/destroy；重複 409 帶現況；僅本人）；`ScanJobCreateSerializer.validate` 加 active 閘門（錯誤訊息指引完成驗證）
- `backend/apps/admin_api/`：`GET domains/`（搜尋/篩選/分頁）＋`POST domains/<id>/override/`（approve→人工核准、reject→否決；`domain_override` Action＋log_admin_action 稽核）
- `backend/config/settings.py`：`ARGUS_DOMAIN_VERIFICATION_TTL_DAYS`（env 可覆寫，預設 90）
- migration `scans/0015_verifieddomain.py`；`uv add httpx`（dnspython 2.8.0 已在依賴）
- 文件同步：backend/CLAUDE.md（路由＋model 速查）、scans/CLAUDE.md（新章節「網域所有權驗證閘門」）、admin_api/CLAUDE.md；需求書 F-036、ER 圖＋表清單（33 表）、差異對照

## 原因

- 初賽評審核心質問：「除了 Google 登入，如何確保使用者擁有目標網站？」——原只有宣告式授權勾選，無技術性驗證。本功能以 DNS TXT/meta tag/HTML 檔三種正規驗證（Google Search Console 式）回答，且與主動測試權限實質綁定；admin 人工覆寫對應問答時承諾的人工審核機制。

## 影響範圍

- **行為改變**：active 掃描現在需要目標網域通過驗證（或 admin 核准）；passive 不受限。既有測試 `test_active_scan_with_extra_authorization_is_recorded` 因新閘門補建立已驗證網域（必要調整）。
- 前端驗證頁 UI 屬後續 wave；目前可經 API 完整操作。

## 驗證方式

- `manage.py check` 通過；`ruff check` 全過
- `test apps.scans.tests_domain_verification`＝35/35；`test apps.scans apps.admin_api`＝759 tests（2 skipped、1 error 為既有 Windows 檔案鎖 flake，已用乾淨 HEAD worktree 對照證實無關）
- 閘門語意測試涵蓋：未驗證/過期/子網域/admin override/他人網域 404/passive 不限
