# 開發歷程改用系統手冊真實專案時程

**日期**：2026-06-10
**操作者**：Claude

## 變更內容

- `backend/apps/content/migrations/0010_seed_real_milestones.py`（新增 data migration）：
  清除舊的 5 個里程碑（MVP 完成 / Hermes-Agent 上線 / 商業化模組 / PWA 與公開頁 / 電子發票 + 載具，
  原本日期全擠在 2026/05），改以手冊「表 4-1-1 專案甘特圖 / 4-1 專案時程」歸納的 **7 個真實里程碑**，
  跨越 **2025/12（114/12）→ 2026/06（115/06）** 共 7 個月：
  1. 2025-12 主題構思與需求分析　2. 2026-01 系統架構與 UI/UX 設計　3. 2026-02 資料庫與後端 API 建置
  4. 2026-03 爬蟲與四維掃描引擎　5. 2026-04 前端 SPA 與互動報告　6. 2026-05 商業化、後台、PWA 與部署
  7. 2026-06 系統整合測試與初評。以 title 為冪等鍵 upsert，reverse 為 noop。
- `backend/apps/content/tests.py`：新增 `test_milestones_seeded_real_timeline`
  （真實里程碑存在、舊里程碑不殘留、時間軸回溯到 2025）。

## 原因

上一輪改了團隊頁真實組員，但 `/project` 頁的「開發歷程」timeline 仍是舊種子——5 個里程碑全擠在 2026/05，
是「最後衝刺做了什麼」而非真正的開發歷程。使用者指出此處未改。依手冊真實 7 個月時程修正。

## 影響範圍

- 公開頁 `/project` 的「開發歷程」timeline（資料由 `/api/content/milestones/` 提供，前端只 render）。
- **純資料**：migrate 即生效、**前端免 rebuild**。後台 `/admin/content`→開發里程碑 可再編輯。
- 不動前端 / API / 其他 model。

## 驗證方式

- `makemigrations --check --dry-run` → No changes detected。
- `test apps.content` → 9 tests OK（含新測試）。
- 本機 `docker compose -p argusnew up -d --build web`（web 啟動自動 migrate 套 0010）後，
  打 `/api/content/milestones/` 確認回 7 個真實里程碑、含 2025 日期、無舊里程碑。
