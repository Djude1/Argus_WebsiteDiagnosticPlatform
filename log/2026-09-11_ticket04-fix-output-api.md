# 票04：修正產出 API（觸發／狀態／產物）

**日期**：2026-09-11  
**操作者**：Claude（ZCode）

## 變更內容
- `backend/apps/scans/fixgen/services.py`：
  - 新增 `trigger_fix_output`：API 觸發入口——啟用閘門（`FixgenDisabledError`）→ 冪等檢查（generating/ready 不計費不派工）→ **先計費再派工**（rebuild 規則：餘額不足不能先讓 LLM 花 token）→ 併發搶輸退回計費。
  - `_fail` 收斂路徑加入 `refund_fixgen_generation`：產生失敗全額退點／額度返還（冪等、退費失敗只記 log 不蓋原因）。
- `backend/apps/scans/serializers.py`：`FixOutputSerializer`（輪詢用，刻意不含 artifacts 本體；ready 才附 `artifact_keys`）。
- `backend/apps/scans/views.py`：ScanJobViewSet 三個 action——
  - `POST /api/scans/{id}/fix-output/trigger/`：503 未啟用、400 非完成掃描／餘額不足（附 required/balance）、202 派工、200 冪等重觸。
  - `GET /api/scans/{id}/fix-output/status/`：idle/generating/ready/failed（含原因）。
  - `GET /api/scans/{id}/fix-output/artifacts/`：ready 才可讀（404）；`?download=llms_txt` 以 attachment/text-markdown 交付，其他鍵下載回 400（片段類交付是複製不是檔案）。
- 文件同步：backend/CLAUDE.md 路由地圖、scans/CLAUDE.md fixgen 職責列。

## 原因
spec 票 04（`.scratch/fix-output/issues/04`）：把引擎（票02）與計費（票03）接線成報告頁可用的 API；「同 ScanJob 重複觸發不重複計費」由觸發層冪等保證。

## 影響範圍
- 僅新增端點，不動既有掃描 API；權限沿用 ViewSet owner 過濾（他人 404）。
- 功能預設關閉（`ARGUS_FIXGEN_ENABLED=false`），trigger 回 503。

## 驗證方式
- `uv run python backend/manage.py test apps.scans.tests_fixgen_api` → 16 tests OK（TDD：先 red——URL 前綴錯誤修正後轉綠；觸發計費冪等、額度優先、不足擋派、owner 限定、狀態輪詢、llms.txt 下載、非檔案鍵下載 400、失敗退點、額度返還後重觸 0 元）。
- fixgen 相關三檔 34 tests OK；完整套件 937 tests 僅 1 個既有環境錯誤；`ruff check` 通過。
