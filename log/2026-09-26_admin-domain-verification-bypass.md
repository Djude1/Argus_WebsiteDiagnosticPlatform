# 管理員測試旁路：staff／superuser 免網域驗證即可主動掃描

日期：2026-09-26

## 變更內容

- `backend/apps/scans/services.py`：`user_owns_domain()` 開頭新增 staff／superuser 旁路——`is_staff` 或 `is_superuser` 一律回 `True`，跳過 VerifiedDomain 查詢。此函式是主動掃描網域閘門的唯一判定點（`ScanJobCreateSerializer.validate` API 層與 `ScanJob.clean()` model 層都走它），單點修改兩道閘門同時生效。
- `backend/apps/scans/tests_domain_verification.py`：新增 `StaffDomainGateBypassTests`（4 案例）：staff API 旁路（201 且不建 VerifiedDomain 紀錄）、superuser 旁路、staff 的 `model.clean()` 旁路、宣告式授權勾選（`active_testing_authorized`）仍必須。
- `frontend/src/features/scans/ScanExperience.jsx`：掃描表單讀取 `useArgusStore` 的 `me`；staff／superuser 在未驗證網域開啟主動模式時，改顯示「管理員測試模式：已略過網域驗證閘門」徽章（複用既有 `scan-verified-badge` 樣式），不再顯示「會被系統拒絕」的阻擋警告。
- 文件同步（同次 commit）：`backend/apps/scans/CLAUDE.md`（閘門小節＋禁止事項表）、`backend/CLAUDE.md`（VerifiedDomain model 速查）、`專題文件生成/需求書_複賽版完整內容.md` F-036（需求說明補句＋驗收方式新增一條）。

## 原因

網域認證功能上線後，對未驗證網域（尤其 Docker 內受控測試目標如 Juice Shop）做主動掃描測試變得困難：現有管道須「先建網域紀錄、再到後台人工核准（admin_override）」兩步。管理員本身已有能力透過 override 核准任何網域，本旁路只是移除這兩步的摩擦，**沒有新增任何權限能力**；掃描與 AuthorizationConsent 紀錄仍歸屬管理員帳號。一般使用者完全不受影響（旁路不觸及他們的路徑）。

## 影響範圍

- 只有 `is_staff` / `is_superuser` 帳號的主動掃描行為改變；passive 掃描、一般使用者的閘門、SSRF／範圍／速率等其他閘門全部不變。
- 宣告式授權（`active_testing_authorized` 勾選）與第三方再確認、coin 預扣等既有流程照舊。
- 不新增 API、model 或 migration；VerifiedDomain 紀錄不會因旁路被建立。

## 驗證方式

- `uv run python backend/manage.py test apps.scans.tests_domain_verification`：39 tests OK（原 35＋新 4）。
- `uv run python backend/manage.py test apps.scans`：735 tests，72 errors 全部為 report_render 缺 CJK 字型（`require_cjk_fonts` RuntimeError，本機 Windows 無 noto-cjk；Docker image 已裝 fonts-noto-cjk）——與本次改動無關的既有環境限制，錯誤全數落在 report 測試類別，無任何 domain／gate／staff 相關錯誤。
- `uv run ruff check backend/apps/scans/services.py backend/apps/scans/tests_domain_verification.py`：通過。
- 前端 `frontend/build-node22.ps1`：build 成功（25.4s，無新 chunk 超限）。
- 文件同步：`rg "測試旁路" backend/CLAUDE.md backend/apps/scans/CLAUDE.md` 兩處一致；需求書 F-036 已補管理員旁路敘述與驗收條目。
