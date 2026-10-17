# 後續修正：JS 端點抽取吃不下 Next.js rewrite 的 :param 形式

**日期**：2026-10-16  
**操作者**：Claude

## 變更內容
- `crawler.extract_api_paths_from_js` 的 `_JS_PATH_RE` 字元類加入 `:` 與 `*`；新增 `_static_prefix_of()` 把抽出的路徑截到第一個含動態參數（`:` 或 `*`）的路徑段之前。`/api_proxy/:path*` → `/api_proxy`；`/api/*` → `/api`；整段動態（`/:locale/x`）→ 空字串、略過。
- 文件：`backend/apps/scans/CLAUDE.md` crawler 列補一句 rewrite `/x/:path*` 形式的處理。

## 原因
15c2a620 的發現層已部署到正式 K8s（PR #2），但對 實測站台 重掃仍 0 偵測。逐段驗證後定位到精確 bug：該站的 API 前綴在 JS 裡只以 Next.js rewrite 規則出現（`source:"/<前綴>/:path*"`），而 `_JS_PATH_RE` 的路徑字元類不含 `:` `*`、又要求路徑後緊接引號，碰到 `:path*` 整個 token 比對失敗 → 前綴完全抽不到 → `api_prefixes` 拿不到 → 不會探 API 文件 → 0 發現。原本新增的測試用裸字串前綴，沒涵蓋 rewrite 形式，所以測試綠燈卻實站漏抓。

## 影響範圍
- JS 端點發現現在涵蓋 Next.js（與類似）rewrite 的動態參數寫法，這是實務上前綴最常出現的形式。
- 不改其他行為；純擴大抽取涵蓋面。

## 驗證方式
- 以真實 rewrite 形式字串驗證整條鏈：`/api_proxy/:path*` → 抽出 `/api_proxy` → `api_prefixes` → `<代理前綴>/v3/api-docs` 等探測目標。
- 新增測試 `tests_js_discovery.py`：rewrite `:param` 形式、`/api/*` 萬用字元、整段動態不產生路徑。
- CI 順序：ruff、`tests/` 36 項、`manage.py check`、makemigrations 無變更皆通過；後端全套 1953 項通過（skipped 12）。沒有改 `k8s/`。

## 下一個待驗證關卡（部署後）
抽取修好後，敏感檔案探測會打 `/<前綴>/v3/api-docs`，但它用 Playwright；此站在 Cloudflare 後面。主爬蟲用 Playwright 這次有爬到 13 頁，所以 Playwright 不是全被擋，探測應該打得到；但**仍需重掃實測確認**。若該探測被 CF challenge 擋下（回挑戰頁而非規格），後續再讓 API 文件探測改用 httpx 式抓取（像測試機驗證那樣直打 200）。此條列為待辦，未在本次改動。

## 備註（安全）
目標暴露仍未修補；本次程式與測試一律用虛構前綴（`/gateway`），不含真實內網 IP。
