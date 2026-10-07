# 已知漏洞補 EPSS 被利用機率與 OSV.dev 修補版本（roadmap 第 9 項之一、§5 第 3 項）

**日期**：2026-10-07  
**操作者**：Claude

## 變更內容
- 新增 `backend/apps/scans/security/vuln_intel.py`，在 `stage_deep_security` 寫入問題前補強兩種已知漏洞問題：
  - 適用範圍：`js-lib-known-vuln`（Retire.js 比對）與 `service-known-cve`（NVD 比對）。
  - **EPSS**（FIRST.org）：
    - 寫入每個 CVE 的被利用機率與百分位，問題層級取最高值寫進 `evidence_json.epss`，描述加一句說明。
    - `priority_score` 最多加 14 分。這比嚴重度之間的最小間距（15）小，所以不會排到更高嚴重度前面。
  - **OSV.dev**（只查 npm，也就是前端函式庫）：
    - 寫入公告數、Retire.js 沒列到的 CVE，以及涵蓋目前版本的最高修補版本（`evidence_json.osv`）。
    - 修法改成「至少升級至 X」。
  - **不改嚴重度**。查不到或服務無法連線時，原樣保留問題，並在 `evidence_json.vuln_intel` 寫明原因。
  - 只送出函式庫名稱、版本與 CVE 編號，不含受測網址；結果以 Django cache 保存 1 天。
- 設定：`ARGUS_VULN_INTEL_ENABLED`（預設開）、`ARGUS_VULN_INTEL_TIMEOUT_SECONDS`（10）、`ARGUS_VULN_INTEL_CACHE_SECONDS`（86400）。
- 文件：security／scans CLAUDE.md、`.env.example`、roadmap §5 第 3 項與第 9 項、需求書 F-013。

## 原因
roadmap：漏洞優先序不能只看嚴重度。EPSS 反映實際被利用的可能性，OSV 提供可執行的修補版本，讓網站主知道先修哪個、升到哪一版。

## 影響範圍
- 有已知 CVE 的掃描，worker 會連到 `api.first.org` 與 `api.osv.dev`。正式環境 worker 的 egress 允許公網 443；有設 `ARGUS_EGRESS_PROXY_URL` 時走代理。
- 已知漏洞問題的排序、描述與修法會比較具體；嚴重度、分數、規則集不變，所以不改 `RULESET_VERSION`、`RENDERER_VERSION`。
- 第 9 項的 Observatory、Analysis Reuse、AI bot 政策尚未開始。

## 驗證方式
- 實際查詢：jQuery 3.4.1 → CVE-2020-11022 EPSS 0.992，排序分數 50 → 63.89（仍低於高風險 75）；OSV 修補版本 3.5.0。nginx 1.18.0 沒有命中 CVE，維持版本暴露問題、不查詢。
- 新測試 `tests_vuln_intel.py`（7 項，不連外）：
  - 嚴重度不變。
  - 修補版本取涵蓋目前版本的區間。
  - 送出內容不含受測網址。
  - 排序不越級。
  - 服務失敗時原樣保留。
  - 有快取。
  - 停用時不呼叫。
  - Retire.js 名稱對應 npm。
- 測試期間抓到並修正一個錯誤：OSV 區間起點為 "0" 時，版本比較的型別錯誤。
- 全套 `uv run python backend/manage.py test apps`：1616 項 OK（2 skipped：真實 ZAP 與另一既有略過），測試輸出中沒有任何對 EPSS／OSV 的實際請求。
- `ruff check backend`（exit 0）、`makemigrations --check`：通過。
