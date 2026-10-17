# ADR-0005 第四刀：放寬 authz 探測端點上限（審計後縮小範圍）

**日期**：2026-10-17
**操作者**：Claude
**依據**：[ADR-0005](../docs/adr/0005-scan-pipeline-tool-integration.md) §3、遷移計畫第 4 刀。

## 審計後的範圍決定
第 4 刀原框為「主動探測合併＋放寬 Nuclei/authz 預算」。動手前審計，三部分價值／風險差很多，只做安全有價值的：

- ✅ **authz 探測端點上限放寬**：使用者解除重抓限制後的清楚贏、低風險，直接提高 BOLA 涵蓋。
- ❌ **Nuclei 放寬（全模板／逐頁）刻意不做**：`CLAUDE.md`「Nuclei 模板治理」已實測全模板 6680 個／
  9535 請求／1–2 RPS 約 80 分鐘，KEV 是 511／628；「只掃根網址」因模板多為站台層級、逐頁只是乘頁數。
  這是噪音與時間的產品取捨，不因不限重抓而該放寬；盲目放寬＝一小時掃描＋大量低訊號＝退步。需明確
  拍板＋實機量噪音的獨立決定，不在本刀。
- ❌ **exposure＋active_probe 階段合併刻意不做**：本就循序、無 RPS 競用，合併是 cosmetic、動覆蓋契約
  與測試、風險不值得。

## 變更內容
- `settings.py`：新增 `ARGUS_AUTHZ_PROBE_MAX_ENDPOINTS`（預設 60）。
- `security/authz_probe.py`：`MAX_ENDPOINTS` 20→60 當預設，新增 `_max_endpoints()` 讀 settings（下限 1），
  `probe_unauthorized_endpoints` 改用它（可被 override_settings 調整）。
- `.env.example`、`security/CLAUDE.md` authz 列同步。

## 驗證
- `tests_authz_probe.py` 加 `MaxEndpointsSettingTests`（預設 60、override 10、0→下限 1）；全 13 項通過。
- `ruff check backend` 通過。改動隔離在 authz_probe＋settings，不影響其他。
- 實際涵蓋提升要在正式環境對有多個 API 端點的授權目標重掃才量得到。

## 備註
60 端點 ÷ active RPS（預設 2）約 30 秒，仍在掃描時間預算內；要再提高由 env 調。
