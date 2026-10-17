# 掃描提速：CDN 後略過 root-URL Nuclei＋提高主動 RPS

**日期**：2026-10-17
**操作者**：Claude
**來源**：使用者回報某授權目標掃描時間由 ~16 分暴增到 ~34 分，附 Codex 的階段耗時分析。

## 核對 Codex 的根因（基本正確）
- **不是跨層去重那刀造成**：去重只在計分前跑一次記憶體合併，對時間無感。
- **agent ~17 分是真工作**：token 計帳修正（`cfa788f4`，非本輪）讓資安專家從「~7 步假性爆表早死」變成
  真的跑完 → 跑出 critical。舊的 16 分有一部分是 agent 壞掉提早結束；**不以 revert 回快處理**。
- **Nuclei ~13 分是結構性浪費**：`stage_active_probe` 原本無條件跑完整 KEV，目標在 Cloudflare 後時
  root-URL 探測停在邊緣、幾乎必 0 發現；且 `ARGUS_ACTIVE_MAX_RPS=2` 與 Katana 對半後 **Nuclei 只有
  1 RPS**，628 個 KEV 請求光速率下限就 ~630 秒。

## 改動（使用者選「提高 RPS + CF 後短路 Nuclei」）
1. **`ARGUS_ACTIVE_MAX_RPS` 2→6**（`config/settings.py`，env 可下修）：Nuclei／Katana 各得 3 RPS，
   敏感檔探測與未授權探測吃全額也一併加速。授權目標是使用者自己的網站，2 RPS 過於保守。
2. **CDN 後略過 root-URL KEV Nuclei**（`ARGUS_NUCLEI_SKIP_BEHIND_CDN`，預設開）：
   - `tasks._behind_waf_cdn`：用爬到的首頁回應標頭（`infra_scanner.detect_edge` 的 `_WAF_CAPABLE`：
     Cloudflare／Akamai／Fastly／CloudFront／Imperva／Sucuri／Azure Front Door；**不含 Vercel／Netlify**
     這類直接代管應用的平台）判定目標前方是全代理邊緣。
   - 命中時 `stage_active_probe` 不跑 Nuclei，改出一筆 info（`_nuclei_skipped_cdn_note`：0 發現不等於
     沒弱點、也不證明防護有效）、覆蓋紀錄 `nuclei=skipped`；Katana 照跑且獨佔整個 RPS 預算
     （`_run_site_active_tools(skip_nuclei=True)`）。
   - 關掉旗標即恢復「跑完再補 WAF 0 發現說明」（`_waf_blocked_nuclei_note`）的原行為。

## 刻意不動
- **agent 的 17 分**：那是跑 critical 的必要成本，砍步數／派工＝少 critical，屬產品取捨；使用者選擇不砍。

## 驗證
- 新增 `tests_coverage.ActiveProbeCoverageTests`：CF 後略過（不呼叫 run_nuclei、覆蓋 skipped、出 info 說明）、
  旗標關閉照跑、無 CDN 照跑。`apps.scans` 全套 1453 通過（skipped 12）；`ruff` 乾淨。
- 既有 Nuclei 測試不受影響（harness 無 crawled_pages → 不判定為 CDN 後 → 照跑）。

## 預期效果（需正式環境實機重掃確認）
- CF 後的授權掃描：省下 Nuclei 的 ~13 分（改為幾秒出 info）；其餘主動探測因 RPS×3 再縮短。
- 粗估總時間由 ~34 分回到 ~20 分上下（agent 的 ~17 分仍在）。實際值以實機為準。

## 備註（安全）
本 log 不含真實站名、真實內部路徑或內網 IP；時間數字取自使用者回報的區間。
