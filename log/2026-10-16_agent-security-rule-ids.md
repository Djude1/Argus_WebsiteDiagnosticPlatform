# AI Agent 資安問題獨立代號、合併重複回報、驗證綁定端點與確定性補位

**日期**：2026-10-16  
**操作者**：Claude

## 變更內容
- **每個 Agent 資安問題有自己的代號**（`backend/apps/agent/findings.py`、`tools.py`）：`agent_security_rule_id()` 依弱點類型（SQL 注入、XSS、越權、外洩…）＋端點路徑算出 `agent-observed-security-<雜湊>`；沒有端點時改用標題。依賴舊代號的地方改用前綴判斷：`runner.py` 派工清單、`reports._assessment_for`、`security/finding_kind.py`、`finding_normalization._renormalize_agent`。`_renormalize_agent` 同時不再把已用工具驗證的高風險降級。
- **合併重複回報**：`consolidate_security_findings()` 把同一次掃描裡同一個問題的多次回報合併成一筆。同一個問題是指代號相同，或同類型且標題相似度 ≥ 0.6。保留最嚴重、已驗證的那筆，`evidence_json.merged_reports` 記合併次數。runner 合併後，計分（`tasks.stage_agent`）與落地共用同一份清單。
- **驗證綁定端點**：`ToolExecutor._confirmed_paths` 記錄主動工具成功打過的路徑；回報的 `url` 路徑必須在裡面，才算「已用主動工具重現」。
- **robots.txt／sitemap 不收**：`report_security_issue` 的 `url` 是這兩類公開索引檔時回 `not_a_security_issue`。工具說明同步寫明。
- **確定性補位**：
  - `security/exposure_scanner.py`：根目錄字典補 `v3/api-docs`。另新增 `api_prefixes()`，從爬取時觀察到的同網站 API 路徑推出前綴（最多 5 個），每個前綴底下探測 5 種 API 規格檔。由 `tasks._observed_api_paths` 提供路徑。
  - 新增 `security/form_scanner.py`，產生 `form-password-unmasked`（中，A04／CWE-549，類型為設定建議）。判定條件：密碼欄位不是 `type="password"`。判斷依據是欄位名稱、id、autocomplete、placeholder、`<label>`，或欄位前 20 字以內的短標題。由 `tasks._analyze_one_page` 的資安分支呼叫。
- **舊資料**：新增 migration `scans/0035_rekey_agent_security_findings`，以歷史 model 把舊代號改成新代號（只改代號、不刪發現，同一個問題的多次回報共用代號），已完成的掃描重算分數與優先清單，並刪除快取報告。`renormalize_findings` 指令同時納入代號回填（`agent_rule`）。
- `RULESET_VERSION` 改為 `2026.10.16`。
- 文件：
  - 模組說明：`backend/apps/agent/CLAUDE.md`、`backend/apps/scans/CLAUDE.md`、`backend/apps/scans/security/CLAUDE.md`。
  - 檢測說明：`docs/hermes-agent-architecture.md`、`docs/scan-stage-checks.md`（第 6、11、15 節）。
  - 競賽文件：`專題文件生成/系統手冊_附錄三_掃描階段與檢測項目.md`、`專題文件生成/需求書_複賽版完整內容.md`。

## 原因
使用者對 ntubimdbirc.tw 掃了三次，結果有四個問題：
1. 第一次同一個 Swagger 外洩出現「嚴重」「中」兩筆，優先處理只列「中」那筆。原因是所有 Agent 資安觀察共用 `agent-observed-security` 一個代號，計分與優先處理依代號去重，只留第一筆，所以「嚴重」那筆不扣分、也不進優先處理。同一個原因還讓報告把所有 Agent 觀察併成一張卡，歷史比較也把不同問題當成同一個。
2. 第二次「sitemap 洩漏登入路徑」重複 3 筆。這不是弱點，卻被寫成「以主動工具重現並確認可被利用」，因為只要任何一個主動工具成功過，之後每一筆回報都算已驗證。
3. Swagger 外洩（`/api_proxy/v3/api-docs`）只靠 AI 偶然發現，三次只找到一次。敏感檔案字典沒有 `v3/api-docs`，也不探測 API 前綴底下的路徑。
4. 「密碼欄位未遮蔽」只在 Agent 的 UX 測試偶然出現，而且被歸在 UX。

## 影響範圍
- Agent 資安問題各自計分，同一次掃描裡多個問題的分數會比修正前低（修正前只扣第一筆）。
- 掃描與報告的規則集版本變了，與舊掃描比較時顯示「評分規則已更新」。
- 正式環境 Argo PreSync `migrate` 會跑 0035，只處理有舊代號的掃描；處理後這些掃描的分數與優先清單會重算，報告在下次下載時重新產生，報告編號不變。
- 敏感檔案探測每個 API 前綴多 5 個請求（最多 25 個），仍受總上限 220 與主動模式速率限制。

## 驗證方式
- 對 ntubimdbirc.tw 實際抓取 `/management/login`：新規則抓到「密碼」欄位（`<p>密碼</p><input type="text">`），帳號欄位不誤判。
- 新增測試：
  - `apps/agent/tests.py`：驗證要對得上端點、sitemap／robots 拒收、代號依問題各自不同、同一問題合併（以 Swagger 實例）、不同問題不合併、計分與優先處理納入每個 Agent 問題。
  - `tests_exposure_scanner.py`：API 前綴推導與探測目標。
  - `tests_form_scanner.py`：真實頁面標記、各種命名方式、不該誤判的欄位。
  - `tests_finding_normalization.py`：migration 0035 回填、重算、重跑不變。
- CI 順序：ruff 通過；`tests/` 36 項通過；`manage.py check` 通過；`makemigrations --check` 無變更；後端全套 1944 項通過（skipped 12，測試資料庫由 migrate 建立，含 0035）。沒有改 `k8s/`，未跑渲染腳本。
- 尚未完成（需正式環境）：Argo 部署後 `migrate` Job `Completed / 0`；對 ntubimdbirc.tw 重新掃描，確認 Swagger 由敏感檔案探測找到、密碼欄位問題出現在資安、Agent 問題不再重複，且優先處理含最嚴重的資安問題。
