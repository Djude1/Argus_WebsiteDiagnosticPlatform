# P0：ZAP 主動掃描逾時治理（大站）

**日期**：2026-10-18
**操作者**：Claude
**來源**：使用者提供 juice-shop／lqll.clouda／imd.ntub 三站掃描報告審查。imd.ntub（50 頁）與先前
ntubimdbirc 的 `zap_active` 都以 `WRN ZAP 主動掃描失敗：ZAP 逾時` 收場；juice-shop／lqll 則完成。

## 根因
`WRN 失敗` 不是掃描 deadline（600s，6 分鐘就失敗、根本沒到）。是 `ZapClient` 的 httpx **單次 HTTP
請求逾時**預設 30s——大站 `importHar`（50 頁 HAR 很大）／`alerts` 讀告警這類重呼叫塞超過 30s，被
httpx 砍斷 → `ZapError("ZAP 逾時")` → `stage_zap_active` 走 except 整段失敗、已得結果全丟。
（stage 本身早已把「掃描 deadline 內沒跑完」正確當 PARTIAL，所以問題不在那。）

## 修法（兩刀，從源頭收斂＋拉長容忍）
1. **拉長 ZAP API HTTP 逾時**：`ARGUS_ZAP_HTTP_TIMEOUT_SECONDS`（預設 120），`run_active` 建 `ZapClient`
   時帶入。大站重呼叫不再被 30s 砍斷。
2. **HAR 節點代表性去重＋上限**：`build_har(representative=True, max_entries=ARGUS_ZAP_ACTIVE_MAX_NODES=40)`。
   `_template_key`（去查詢字串、數字段換 `#`）把「同一支模板吃不同 id」的近似頁（`/p/412-1043-6298.php`
   與 `/p/412-1043-72.php`、`/rest/products/1` 與 `/rest/products/2`）收斂成一個代表節點，active scan 的
   節點數不再被大站幾十頁灌爆——import 更小、掃更快、也更不會觸發 HTTP 逾時。被動分析不傳這些參數、
   行為完全不變。

## 刻意不做
- 不改掃描 deadline（600s）與 PARTIAL 邏輯（本來就對）。
- 不在 CDN 後略過 ZAP 主動：實測 lqll（Cloudflare 後）ZAP 主動仍能完成並 +1，與 Nuclei 不同，不該一律略過。

## 驗證
- `tests_zap_passive.BuildHarTests` 新增 3 項：模板去重、max_entries 上限、被動預設不去重；
  `apps.scans.tests_zap_passive` 17 項通過，ruff 乾淨。
- 實機待使用者部署新 image 後對 imd.ntub 這類大站重掃確認 `zap_active` 不再逾時失敗（需 backend rebuild）。

## 本輪三站審查重點（併記）
- juice-shop（Angular SPA 漏洞靶站）：資安 35／ZAP +4／exposure 4／authz 2，深度全開、幾乎全真陽性；
  但只爬到 2 頁（SPA 無連結、無 sitemap），內容四維樣本不足、AEO 未充分評估 → 列為後續 P1「SPA 路由發現」。
- lqll.clouda（Spring Boot + CF）：資安 20 項判定合理；爬取偏慢（28.7 秒/頁）。
- imd.ntub（PHP 多頁）：log 360 項但報告正確去重成 29 項、無高危，乾淨不膨脹；ZAP 主動逾時＝本次修的目標；
  SEO 連結 199 條有 147 條未檢查（大站預算）→ 後續 P2。

## 備註
不含真實站名以外的機密值；未新增對目標的攻擊面，只調整送進 ZAP 的節點數與 API 逾時。
