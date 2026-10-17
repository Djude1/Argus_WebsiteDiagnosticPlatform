# ADR-0005 第三刀：退 ZAP 被動階段、獨有規則移植成自家被動檢查

**日期**：2026-10-17
**操作者**：Claude
**依據**：[ADR-0005](../docs/adr/0005-scan-pipeline-tool-integration.md) §2、遷移計畫第 3 刀。

## 背景與審計
原本 `zap_passive` 與自家被動（`site_security`／`deep_security`）並存，靠 13 條 `OVERLAP_RULES`
手動抑制重疊告警。審計發現：**ZAP 被動的「重複發現」早已被抑制表解掉**，退階段屬「移除多餘引擎
＋補其獨有規則」，不是修去重。逐條查過，自家還沒覆蓋、退掉會漏檢的 ZAP 獨有規則有 4 條，須先移植。

## 變更內容

### 新增 `security/passive_checks.py`（只讀已抓頁面、零新請求）
- `analyze_mixed_content`→`security-mixed-content`（A02／CWE-319）：HTTPS 頁載入 http:// 子資源；
  active 類（script／iframe／object／embed／stylesheet link）中風險、passive 類（img／video…）低。
- `analyze_sensitive_url_params`→`security-sensitive-url-param`（A05／CWE-598）：頁面網址與連結／GET
  action 的查詢字串帶 password／token／apikey／secret／session 等敏感參數名；值一律遮罩。
- `analyze_error_disclosure`→`security-error-disclosure`（A05／CWE-209）：頁面 HTML 含堆疊追蹤／框架
  除錯頁，重用 `api_scanner._stack_kind`（api_scanner 只看 API 回應，這裡補一般頁面）。
- `analyze_passive_html` 彙整，單一子檢查例外不影響其他。

### `header_scanner`
- 加 Permissions-Policy 缺失 `header-permissions-policy`（A05／CWE-693，低；ZAP 10063 移植）。

### owasp_mapper／finding_kind
- 4 條新規則補 OWASP／CWE 對映與類型（mixed-content/permissions-policy=config、其餘=exposure；
  header- 前綴由既有 `_PREFIXES` 自動歸 config）。

### 退役 `zap_passive` 階段（`tasks.py`）
- 移除 `stage_zap_passive`、`_runs_zap_passive`、SCAN_PIPELINE 的 `zap_passive`、planned step、
  `run_passive` 匯入；HAR 暫存目錄改只在 `_runs_zap_active` 時建立（被動已不需要）。
- `stage_deep_security` 的 findings 併入 `analyze_passive_html(ctx.crawled_pages)`。
- 工具版本改由 `stage_zap_active` 寫 OWASP ZAP。
- `zap_passive.py` 模組**保留**（`ZapClient`／`build_har`／`alerts_to_findings`／`OVERLAP_RULES` 仍供
  `zap_active` 用；`run_passive` 保留未接線）。ZAP 10027「註解可疑字詞」不移植（低訊號、秘鑰已另覆蓋）。

## 驗證
- 新增 `tests_passive_checks.py`（11）：混合內容 active/passive/乾淨/非 HTTPS、URL 敏感參數命中/乾淨、
  錯誤洩漏命中/乾淨、Permissions-Policy 有/無。
- 更新 `tests_pipeline_stages`（階段順序去 zap_passive）、`tests_zap_passive`（移除 StageTests，保留
  模組與 run_passive 測試）、`tests_security_scanners`（clean headers 補 permissions-policy 兩筆）。
- `apps.scans`＋`apps.agent` 全套 1526 通過（skipped 12）；ruff 通過。
- 覆蓋契約：`coverage.py` 的 `zap_passive` 標籤保留（舊掃描顯示用），只是不再被標記。

## 備註（安全）
測試用虛構網址（site.example.test）；不含真實站名、路徑或秘鑰。
