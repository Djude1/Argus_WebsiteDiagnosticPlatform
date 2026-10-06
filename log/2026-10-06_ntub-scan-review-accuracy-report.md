# ntubimdbirc.tw 實掃審查：判定準確度、CDN／WAF 偵測、做得好的地方、精準標註、報告改版

**日期**：2026-10-06  
**操作者**：Claude

## 掃描與限制
- 正式站（argus.clouda.dpdns.org）登入受 Cloudflare Turnstile 保護，本次雲端環境的網路政策拒絕 `challenges.cloudflare.com` 子網域，無法登入；改以同版程式在本機（eager 模式）對 https://ntubimdbirc.tw/ 實掃（scan 43／44／45，各 13 頁）。
- 本機出網經代理，TLS 檢查看到的是代理憑證（SSL 到期天數、TLS 版本不代表正式結果）；其餘 HTTP、DNS、頁面內容為實際結果。

## 獨立審查結論（逐項以 curl／DNS 查詢與頁面原始碼核對）
- **誤報**：①註冊表單 placeholder `e.g.0911-222-333` 被當成個人手機；②隱私權頁的組織信箱 `ntubimdbirc@ntub.edu.tw` 被當成個人資料；③子網域 domjudge 對 HEAD 斷線、GET 正常（302），被判「無法連線」；④SSL 剩 30 天以內一律 high，但 Let's Encrypt／Cloudflare 自動續期憑證本來就在剩 30 天時續期；⑤`alt=""`（合法的裝飾圖寫法）114 張被算成「缺少 alt」；⑥手機抽屜選單（移出視窗外）的連結被算成觸控目標過小。
- **漏報**（SEO 分析頁明細有、問題清單與報告沒有）：4 個站內連結 404（/service/0～3）、www 與非 www 都直接 200、og:url／robots／sitemap 宣告 www 但網站用非 www、12 頁 title 都是「NTUB BIRC」、HSTS 標 preload 但 max-age 只有 180 天。
- **產品 bug**：爬到 0 頁仍標「完成」並給 73 分。
- **網站做得好的地方**：Cloudflare（CDN／反向代理、具 WAF 能力）、HTTPS＋301、HSTS、nosniff、DNSSEC、SPF -all、robots＋sitemap、自訂 404、載入快。

## 變更內容
- 判定準確度：`scanners.py`（placeholder 不掃 PII、組織／角色信箱、`alt=""` 與缺 alt 分開，大圖空 alt 只提醒）、`seo/link_check.py`（HEAD 連線層錯誤改 GET）、`security/ssl_scanner.py`（15–30 天 info、≤14 medium、≤7 high、過期 critical）、`security/header_scanner.py`（HSTS preload 不合格 info）、`crawler.py`（移出視窗的元素不算觸控目標）。
- 漏報轉成 Finding：`seo/site_findings.py`（站內失效連結、www 重複、宣告主網址不一致、重複 title），在 `stage_seo_links` 寫入。
- 0 頁不再「完成」：`tasks._ensure_usable_pages` → `ScanTargetUnreachable` → `finish_unreachable`（失敗、可讀原因、全額退款）。
- 網站概況：`security/infra_scanner.py`（A／AAAA／CNAME／NS、IP 反解、Cloudflare 網段、標頭／CNAME 指紋 → 邊緣或主機＋提醒文字）、`site_profile.py`（做得好的地方，不與同次問題矛盾、只列有勾的維度）、`dns_scanner.email_dns_posture`、`ScanJob.site_profile`（migration 0026）、`stage_site_profile`、`ScanJobSerializer.site_profile`。
- 精準標註：爬蟲記錄觸控目標／缺標籤欄位／破版元素的行動版文件座標，有這類問題時另拍行動版截圖（`layout_metrics.mobile_screenshot`）；Finding `evidence_json.annotations`；API `screenshot/?variant=mobile`、`PageSerializer.has_mobile_screenshot`；前端 `ScreenshotCanvas` 切到行動版截圖逐一框住元素並標尺寸。
- 前端：`components/scans/SiteProfilePanel.jsx`（網站架構＋做得好的地方），樣式 `legacy-member/94-report-style.css`；重新產生 `openapi.json`／`apiTypes.ts`（同時補上先前漏產的 `/api/domains/gsc/*`）。
- 報告改版（`report_render/`，`RENDERER_VERSION` 5）：`theme.TYPE` 字級層級、移除所有彩色左邊條、中風險以上完整卡片／低風險與資訊精簡條目、第一章新增「做得好的地方」「網站架構」（`payload.site_profile`、schema 同步）、附錄驗證表只列中風險以上。ntubimdbirc.tw 由 25 頁降到 19 頁。
- 文件：`backend/apps/scans/CLAUDE.md`、`security/CLAUDE.md`、`backend/CLAUDE.md`、`frontend/CLAUDE.md`、`專題文件生成/需求書_複賽版完整內容.md`（F-013／018／019／021）。

## 驗證方式
- 後端：`ruff check backend`、`makemigrations --check`、`manage.py test apps` 全過；新增 `tests_site_profile.py`、`NoUsablePagesTests`、`SeoSiteFindingsTests`、PII／SSL／HSTS／HEAD fallback／精準標註測試。
- 前端：`npm run lint`、`typecheck`、`npm test`（31 檔 211 項）、`vite build` 通過。
- 本機實掃 scan 44／45：誤報消失、新 SEO 問題出現、site_profile 判定 Cloudflare Edge（4 個 IP 在 Cloudflare 網段＋cf-ray）、觸控目標標註座標全在 375px 內；瀏覽器實測網站概況面板與行動版逐元素標註、390px 無水平捲動；PDF 報告 19 頁人工檢視。

## 尚未完成
- 正式站實掃：需要在雲端環境網路設定放行 `challenges.cloudflare.com`，或由使用者在正式站手動執行一次掃描比對。
- 部署後既有掃描的報告會因 `RENDERER_VERSION` 變更自動重產；舊掃描沒有 `site_profile`，報告與畫面不顯示該區塊（需重新掃描）。
