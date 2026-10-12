# API 端點清單：補進 PDF 報告、資安分析頁說明沒資料的原因

**日期**：2026-10-12  
**操作者**：Claude

## 變更內容
- `reports._report_api_surface` → `appendix.api_surface`；`report_render/report.py` 附錄新增「API 端點清單」小節（技術索引之後），`schema.json` 補欄位，`RENDERER_VERSION` 31
- `projects.project_security` 新增 `api_check`（`coverage.checks.api_passive` 的狀態與原因）
- `ProjectSecurityPage.jsx`：勾資安的掃描一律顯示「API 端點」區塊；沒有清單時依狀態說明（頁面沒呼叫 API／檢查沒完成／功能上線前的掃描）
- `crawler._observe_api_response`：排除 Cloudflare 注入的 `/cdn-cgi/` 端點
- 測試：`tests_api_passive.py`（cdn-cgi、api_check、報告附錄 3 項）、`ProjectSecurityPage.test.tsx`（3 項）

## 原因
使用者自掃 argus.clouda.dpdns.org 後，資安分析頁與報告都看不到 API 端點清單：
- 報告：當初只做了網頁，沒有放進 PDF（遺漏）
- 網頁：沒有清單時整塊隱藏，看不出是沒跑、沒觀察到還是舊掃描
- 用修改後的爬蟲實爬正式站，確認有記到 `/api/auth/refresh/` 與 Cloudflare 的 `/cdn-cgi/rum`；後者不是網站的 API

## 影響範圍
- 舊報告快取因 `RENDERER_VERSION` 31 重新產生
- 部署前完成的掃描不會有清單，頁面會提示重新掃描

## 驗證方式
- 本機真實 Chromium 對測試站與正式站實爬，確認 `api_observations` 有資料
- `manage.py test apps.scans apps.agent`：1430 項 OK（skipped 10）；`ruff check backend` 通過
- 前端 lint（0 error）、typecheck、`npm test` 283 項通過
