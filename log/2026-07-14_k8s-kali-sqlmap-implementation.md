# K8s Kali SQLmap 實作紀錄

**日期**：2026-07-14
**操作者**：Codex

## Task 1：安全結果契約、遮罩與設定

### 變更內容

- 新增 `backend/apps/scans/security/kali_contracts.py`，定義 SQLmap 目標、結果、執行結果、保留結果與 executor protocol。
- 新增嚴格的 runner JSON 邊界：限制 16384 bytes、固定 schema 與欄位、驗證索引與安全字元，並將不可信資料轉成 `KaliResult`。
- 新增 URL query value 遮罩；保留 origin、path 與 query key，移除 fragment，避免完整參數值進入證據或紀錄。
- `KaliResult.as_dict()` 固定輸出既有八個欄位，且永不回傳 raw stdout；本 Task 不加入 `correlation_id` 或 `tool_version`。
- 新增 Kali backend、namespace、runner image、SQLmap 版本、timeout、鎖、預算、TTL、結果大小與 Redis URL 設定；功能及 backend 預設維持停用。
- 更新 `.env.example`，列出可由環境設定的 Kali 安全預設值。
- 新增 `backend/apps/scans/tests_kali_contracts.py`，鎖定 URL 遮罩、stdout 隔離及 runner payload 拒絕行為。

### 原因

在加入 Docker 與 Kubernetes executor 前，先建立兩者共用且可驗證的安全結果契約，避免不可信 runner 輸出、URL query value 或 raw SQLmap stdout 被持久化或傳遞到後續流程；同時讓尚未完成 Secret at-rest encryption 的環境維持 disabled-by-default。

### 影響範圍

- 影響 `scans.security` 後續 Kali policy 與 executor 的共用型別及 parser 邊界。
- 影響 Django Kali 設定與 `.env.example` 範例；無 migration、套件、billing、前端或既有 scanner 行為變更。
- 本 Task 尚未把新契約接入既有 `kali_tools.py`；後續 Tasks 依計畫完成 facade 與 executor 整合。

### 驗證方式

- RED：`uv run python backend/manage.py test apps.scans.tests_kali_contracts -v 2` → exit 1，因 `apps.scans.security.kali_contracts` 尚不存在而出現預期 `ModuleNotFoundError`。
- GREEN：同一 focused test 命令 → 3 tests，全部通過。
- Ruff 首跑：指定三檔檢查發現一項 `UP035`；最小修正 `Sequence` import 後重跑通過。
- 指定 Ruff：`uv run ruff check backend/apps/scans/security/kali_contracts.py backend/apps/scans/tests_kali_contracts.py backend/config/settings.py` → `All checks passed!`。
- Django：`uv run --frozen python backend/manage.py check` → 0 issues。
- 相關回歸：`uv run --frozen python backend/manage.py test apps.scans.tests_kali_contracts apps.scans.tests_kali_tools -v 1` → 23 tests，全部通過。
- 全 backend Ruff：`uv run --frozen ruff check backend` → `All checks passed!`。
