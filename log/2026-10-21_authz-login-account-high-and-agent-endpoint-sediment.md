# 未授權 API 外洩：登入帳號名單升 high ＋ Agent 端點沉澱成確定性重探（修掃描不穩定）

**日期**：2026-10-21
**操作者**：Claude

## 問題
使用者連續掃 ntubimdbirc.tw，`/members/all`（匿名回傳全體後台登入帳號含管理員 `bircadmin`）每次嚴重度不一：有時嚴重、有時高、這次只有中、有時整個不見。

## 根因（兩個，疊在一起）
1. **嚴重度判定**：確定性 `authz_probe.analyze_unauthorized_results` 的 high 條件只看「有 PII／敏感欄位名（password/token）／強個資／內部 IP」。一份成批後台帳號名單，欄位是 `userAccount`／`roleId`／`enable`，命中「身分＋內部欄位」只算 qualifies（成立），但沒有上述升級訊號 → **medium**。也就是連確定性層都只會給中。登入帳號是憑證的一半，匿名可撈走全體（含管理員）帳號，應是 high。
2. **穩定性**：這條端點這次是 **AI Agent** 觀察到的（`agent-observed-security-*`）——雜湊 rule_id 會漂、嚴重度封頂 medium、且 ADR-0006 分數分離後不計分。確定性 authz 探測只在該端點的前綴（`/api_proxy`／`/backend`）這次出現在流量／JS／OpenAPI 規格時才會打到；沒打到就只剩 Agent 那筆中風險，Agent 也沒打到就整個消失。`_previous_deterministic_endpoints` 只重探「上次確定性層」找到的端點，**明確排除 Agent 觀察**，所以 Agent 偶然打到的永遠沉澱不下來。

## 變更
- `backend/apps/scans/security/authz_probe.py`（Fix 1）：新增 `_LOGIN_ACCOUNT_KEYS`（userAccount／username／帳號／acct…）與 `_ADMIN_HINT`。成批記錄已 qualifies（後台名單）且欄位含登入帳號 → 升 **high**；證據與描述點明「回傳欄位含登入帳號」，名單含管理／特權帳號時另點明。公開姓名目錄不受影響（它不 qualifies）。
- `backend/apps/scans/tasks.py`（Fix 2）：新增 `_previous_agent_security_endpoints(scan_job)`——讀上一次完成掃描帶 `observed_endpoint` 的 `agent-observed-security-*` 發現端點，`_run_authz_probe` 併入無憑證探測候選。一旦任何一層（含 Agent）發現過該端點，之後每次掃描都由確定性層重探；仍存在就穩定報 `security-unauth-api-records`（計分、嚴重度由內容決定，登入帳號名單＝high）。
- `backend/apps/scans/versions.py`：`RULESET_VERSION` → `2026.10.21`（改了嚴重度判定）。
- 測試：`tests_authz_probe` 加 `test_login_account_dump_escalates_to_high`（既有 `test_member_dump_flagged` 無登入帳號欄位，仍 medium，維持不破）；`tests_coverage` 加 `PreviousAgentEndpointsTests`（收集上次 Agent 端點、無上次掃描回空）。
- 文件：`scans/security/CLAUDE.md`、`scans/CLAUDE.md` 同步。

## 為什麼這樣就穩定
兩個修法合起來：端點被發現過 → 下次確定性層一定重探（Fix 2）→ 仍可讀就報，且因含登入帳號一定是 high（Fix 1）、計分、代號固定（`security-unauth-api-records` 不是會漂的雜湊）。不再依賴「這次 Agent 有沒有剛好打到」。

## 殘留限制
若某端點從未被任何一次掃描（流量／JS／規格／Agent）發現過，仍探不到——這是確定性探測的本質（不亂猜路徑）。但只要出現過一次就會固定下來。

## 驗證
- `ruff check`：authz_probe／tasks／tests 全過。
- `manage.py test apps.scans.tests_authz_probe apps.scans.tests_coverage apps.scans.tests_pipeline_stages apps.scans.tests_scoring_and_report_grouping apps.scans.tests_scoring_versions`：119 pass。
- 未自動驗證：需部署後對 ntubimdbirc.tw 重掃一次全站＋主動，確認 `/members/all` 穩定由確定性層報成 high、計入資安分數，不再隨機變中或消失。
