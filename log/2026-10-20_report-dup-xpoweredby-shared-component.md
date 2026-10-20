# 報告審查修正：X-Powered-By 重複列兩項、axe 同一元件 47 頁逐頁列

**日期**：2026-10-20  
**操作者**：Claude

## 變更內容
- `security/header_scanner.py`：X-Powered-By 帶版本（`PHP/8.1.34`）時不再開 `header-x-powered-by`，交給 `service_cve_scanner` 的 `service-version-exposed`（含 CVE 比對）；沒有版本的值（Express）照舊。
- `root_causes.py`：`service-version-exposed` 併入「網站伺服器的回應標頭設定」群組。
- `reports._shared_component`：元件型規則（`axe-`、`ux-fake-button`、新增 `UX_JAVASCRIPT_`）只比證據第一行（第一個元素）；非元件型規則仍要整段相同。
- 測試：`tests_security_scanners`（帶版本／不帶版本各一）、`tests_root_causes`、`tests_report_site_metrics`（axe 三頁其中一頁多一個元素仍收成全站共用元件）。
- 文件：`apps/scans/CLAUDE.md`、`apps/scans/security/CLAUDE.md`。

## 原因
2026-10-19 cs.ntust.edu.tw 實掃報告審查：4.3「php 8.1.34 版本資訊外洩」與 4.6「X-Powered-By 洩露技術資訊」是同一個標頭、同一個修法，且 4.3 沒進「改一處就能一起解決」；4.12 axe `aria-required-parent` 47 頁都是同一顆 `.owl-dot` 輪播按鈕卻逐頁列 5 處、「另 42 處」，4.17 同類卻正確收成「全站共用元件」——差別只在各頁被 axe 列出的元素數不同，整段逐字比對配不起來。

## 影響範圍
- 資安問題數：有版本的 X-Powered-By 網站少一項低風險（原本重複）；分數受影響極小（低風險 −4 一次）。`RULESET_VERSION` 未改：判定規則本身沒變，只是去重。
- 報告：元件型規則更常收成「全站共用元件」；不需升 `RENDERER_VERSION`（資料層）。

## 驗證方式
- `uv run ruff check backend` 通過；`manage.py test apps.scans` 1518 項通過（12 skipped）。
