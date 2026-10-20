# Agent 把 WAF 攔截頁回顯的掃描器出口 IP 報成「內部 IP 外洩」：認出口 IP、降級、合併

**日期**：2026-10-20  
**操作者**：Claude

## 變更內容
- `security/ip_context.py`：新增 `_scanner_networks`／`is_scanner_ip`／`only_scanner_ips`，`describe_ips` 對 `ARGUS_SCANNER_EGRESS_IPS` 內的 IP 判讀為「Argus 掃描器自己的出口位址，不是內部 IP 外洩」。
- `agent/tools.py`：`scanner_ip_disclosure`＋`SCANNER_IP_NOTE`；`report_security_issue` 的觀察在講 IP 外洩、證據 IP 全是出口位址時降為 info 並附說明。
- `scans/finding_normalization._renormalize_agent`：既有掃描同一規則（冪等，不重複附註），部署後跑 `renormalize_findings --scan-id N` 可修舊掃描。
- `agent/findings.same_issue`：同類型、標題不夠像但證據片段去數字後相似度 ≥ 0.9（`_EXCERPT_SIMILARITY`）也算同一問題——同一個 WAF 攔截頁從兩條路徑各觸發一次只差時間戳。
- `k8s/01-namespace-config.yaml`：`ARGUS_SCANNER_EGRESS_IPS: "211.75.1.199"`（使用者確認的正式出口；本來就是公開頁 `/scanner` 要列的資訊）。
- 測試：`tests_ip_context`（出口 IP 判讀、未設定時不判）、`agent/tests`（降為 info；兩路徑同攔截頁合併成一筆）、`tests_finding_normalization`（重算降級、冪等）。
- 文件：`apps/agent/CLAUDE.md`、`apps/scans/security/CLAUDE.md`、`k8s/README.md`。

## 原因
2026-10-19 cs.ntust.edu.tw 實掃報告 4.1／4.2：WAF 406 攔截頁回顯 211.75.1.199，Agent 報成「後端伺服器內部 IP 外洩」（中風險）兩次；使用者確認該 IP 是 Argus 的出口。程式原本只核對「是否在網站公開 DNS」，沒有「是不是我們自己」這一項，ConfigMap 也沒填出口 IP。

## 影響範圍
- 只影響 Agent 觀察（不計入基準分）；降為 info 後不進優先處理清單。
- 出口 IP 變動時必須同步 ConfigMap，否則回到「需人工確認」的保守判讀（不會誤判成內部外洩，只是不會自動降級）。

## 驗證方式
- `uv run ruff check backend` 通過；`manage.py test apps.scans apps.agent apps.content` 1644 項通過（skipped 13）。
- 根目錄 `tests/` 36 項：35 通過，`test_kali_k8s_contract` 因本機沒有 kubectl 的既有環境錯誤。
- 未做：正式站部署後對該掃描跑 `renormalize_findings`、重下載報告確認 4.1／4.2 合併成一筆資訊提示。
