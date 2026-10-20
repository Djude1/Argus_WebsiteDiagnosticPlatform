# 提供測試帳密時先登入、整站以登入狀態重跑

**日期**：2026-10-20
**操作者**：Claude

## 變更內容
- 新增 `backend/apps/scans/crawler_auth.py`（純函式）：`login_candidate_urls`（起始頁→頁內登入連結→常見登入路徑，同源去重設上限 6）、`html_has_password_field`、`extract_login_links`。
- `backend/apps/scans/crawler.py`：
  - `_make_context`／`_recycle_context` 新增 `storage_state` 參數，有值時每個 context 都帶登入後的 cookies／localStorage。
  - 新增 `establish_login_state`（開 throwaway context，依候選網址找密碼欄位、填帳密送出，成功即回 `storage_state`）與 `_attempt_form_login`（只操作 Playwright 欄位）。
  - `crawl_site` 新增 `login_credentials` 參數；有帳密時先登入取 `storage_state`，之後所有 context（含 recycle）沿用；結果記 `warnings["authenticated_crawl"]`（attempted／ok／login_url／reason）。
- `backend/apps/scans/tasks.py` `stage_crawl`：解密 `test_auth_*` 傳 `login_credentials`，並依登入結果寫 log（成功／未成功改未登入繼續）。
- 前端 `ScanExperience.jsx`：測試帳號區塊的說明改寫為「先登入、整站以登入狀態重跑」；只在主動模式送出帳密（網域已驗證＝可登入自家網站的閘門）不變。
- 測試 `backend/apps/scans/tests_crawler_auth.py`：候選網址、密碼欄位偵測、登入連結抽取。

## 原因
使用者要求：提供測試帳密時，爬蟲要先登入、再以登入狀態把整個掃描重跑，涵蓋登入後才看得到的頁面。原本 `test_auth_*` 只注入 AI 深度代理的 `auth_idor`／`logic_abuse` 兩個角色 prompt，對爬蟲與逐頁檢查完全沒作用，且需要一串閘門（agent 總開關、深度 opt-in、模型真的去登入）才會生效，使用者感覺「沒效果」。

## 影響範圍
- 觸發條件：`ScanJob` 有 `test_auth_*`（前端只在主動模式送）。登入態套用到爬蟲與所有以爬取頁面為輸入的檢查（SEO／AEO／GEO／UX／被動資安）。
- **判斷取捨**：確定性的敏感檔案探測（exposure）與未授權存取探測（authz）**維持匿名**，因為它們的意義是「沒登入能拿到什麼」，套登入態會失去意義。已在 log／文件註明。
- 安全：登入導覽走既有 context 的公開目標政策＋同源攔截；帳密只解密注入 Playwright 表單，不落 log／DB／報告；`storage_state` 只在記憶體傳遞。登入失敗只回 ok=False、不中斷掃描。
- HAR（ZAP 主動用）現在可能含登入後流量；`zap_passive.build_har` 既有邏輯已去除 Cookie／Authorization 並遮罩 Set-Cookie，HAR 掃完即刪，無需改動。

## 驗證方式
- `uv run ruff check`（crawler、crawler_auth、tasks、tests）：All checks passed。
- `manage.py test apps.scans.tests_crawler_auth apps.scans.tests_pipeline_stages`：16 pass。
- `apps.scans.tests_crawl_budget tests_site_projects`：35 pass（3 skip）。
- 前端 `npm run lint`（0 error，1 個既有無關 warning）、`typecheck`（clean）、`vitest ScanJobForm.test.tsx`（10 pass，含「被動模式不顯示測試帳密欄位」）。
- 未自動驗證：真實網站的表單登入成功率（登入表單樣式多變、SSO／多步驟登入不保證成功；登入失敗會改未登入繼續並記錄）——需實機對有登入的授權目標確認。
