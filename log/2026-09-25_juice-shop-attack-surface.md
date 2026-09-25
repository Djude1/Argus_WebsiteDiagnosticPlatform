# Juice Shop 攻擊面打通與 agent 能力強化（第二波）

**日期**：2026-09-25
**操作者**：ZCode（GLM-5.3）

## 變更內容

四個 commit（1747060／183d15e／4af38de／本次）：

1. **`1747060` 攻擊面打通三件套**
   - `crawler.py`：`crawl_site` 每頁掛 `page.on("response")` 被動收集 same-origin XHR/fetch 端點（上限 80、零新請求），回傳值擴為 4 元組
   - `tasks.py`：`discovered_endpoints` 併入 `crawled_urls`，自動流向 Nuclei extra_urls 與 sqlmap 候選
   - `agent/tools.py`：新增 `get_network_requests` 工具（ToolExecutor 被動記錄 same-origin XHR/fetch，method/URL/status，上限 200；持久化前 `redact_url_query_values` 遮罩）
   - `agent/runner.py`：`SECURITY_FIRST_PROMPT` 改為描述工具能力（SPA 端點在流量裡），移除舊版具體端點例子——給感知不給答案
2. **`183d15e` 字典補強**：`ftp`／`ftp/`／`metrics` 進 BUILTIN_SENSITIVE_PATHS；新增 `exposure-endpoint-metrics` 分類（Prometheus 純文字輸出無法靠目錄列表判定）
3. **`4af38de` sqlmap --level=3**：裸 `--batch` 對空值 query 參數（`?q=`）2~3 秒即誤判不可注入；level 3 實測可確認 boolean-based blind SQLi。demo 疊加 `AGENT_MAX_STEPS=40`／`MAX_TOKENS=250k`
4. **`（本次）` agent 反空轉＋token 壓縮＋目錄列表格式**
   - `loop.py`：`_compact_stale_tool_results`（每種觀察工具只留最新全量快照）；`_inject_stall_hint_if_needed`（連續 ≥4 次同型 click/type_text 注入一次策略導正）
   - `exposure_scanner.py`：`_looks_like_directory_listing` 補 Express serve-index 的 `<title>listing directory` 格式
   - `docs/research-dast-llm-pentest-2026.md`（新增）與 `docs/competitive-positioning.md`（更新對打數據）

## 原因

使用者目標：對手以經典 GitHub 工具整合即能重現應用層攻擊（SQLi／存取控制），
Argus 串接 AI agent 必須更強。#11 診斷：攻擊工具「有執行但攻擊面為零」——
SPA 的 API 端點不在爬蟲結果，sqlmap 候選全是無參數首頁；agent 的
SECURITY_FIRST_PROMPT 要它找的帶參數連結在 SPA DOM 裡不存在。

## 影響範圍

- 所有 SPA 網站的主動掃描（攻擊面輸入從「頁面連結」擴及「真實 API 流量」）
- sqlmap 驗證品質（level 3；正式環境同樣生效——風險維持 risk=1 無 OR 注入）
- Agent 迴圈的 token 效率與空轉防護（正式環境同樣生效）
- `crawl_site` 回傳簽名變更（4 元組）：三個測試檔 mock 已同步

## 驗證方式

- 掃描 #12：XHR 攔截生效（觀察到 10 端點）但 sqlmap 裸參數誤判；agent 22 步被 20 上限切斷
- 掃描 #13：**SQLi CRITICAL 首次工具確認**（2 target confirmed=True）＋ metrics 洩漏；agent 32 步爆 token（260k）→ 診斷出快照累積與 selector 空轉
- 掃描 #14（最終）：**18 findings（1C+2H+8M+5L+2I；報告合併同名 rule_id 後 17）**——SQLi critical＋目錄列表 ×2（Express 格式修正生效）＋metrics；**agent 36 步 169k tokens 完整完成＋回報 1 UX issue**（進到忘記密碼流程）
- 報告 #14：17 頁 Word 下載 OK；視覺驗收 17/17 頁 pass（SQLi critical 紅標＋sqlmap 證據＋修補建議齊備；中文圖表正常）
- 測試：agent 42＋exposure 20＋kali pipeline/tools/settlement/scan_plan 49 全過；全套（背景）見任務紀錄

## 已知限制與後續

- 存取控制類（跨帳號讀寫、負數數量）需登入態多角色測試——後續功能（agent 帶認證 context）
- 對手「Unix 時間戳／/public/／x-recruiting」資訊類未涵蓋——屬 header fingerprint 加強項
- 建議下一波：whatweb（指紋→CVE）＋ffuf（內容發現）整合（調研結論，優先於 wapiti/Nikto/ZAP）

---

## 追記（第三波：#15→#16，未授權存取驗證與穩定性）

**變更**（commit 7df2f38／a3d1055 前後／證據修復）：
- `probe_unauthorized_access(url)`：無 cookie/token 匿名重放同源端點，回應觀察
  （status/content-type/片段，遮罩後）由 agent 判斷是否未授權存取——同源閘＋
  deep_mode schema 隔離＋runtime 再驗、不跟隨 redirect、單次 GET
- `report_security_issue`：觀察型資安回報（critical 封頂 high、必填缺失拒絕、
  URL query 遮罩），走 persist_agent_security_findings 落地鏈
- header_scanner：x-recruiting／x-generator／x-aspnet-version 指紋規則
- sqlmap timeout 120→240s（demo）：level3 完整驗證 87~120+ 秒浮動，
  #15 兩度邊緣超時導致 critical 時有時無
- kali_tools evidence 修復：fallback SQLi finding 的 evidence 原為空字串
  （報告「檢測依據」空白），改填 json.dumps(evidence_summary)

**驗證**：
- #15：header-x-recruiting 生效；agent 8 步精準完成（3 個 unauthorized probe
  判斷正確零誤報）；但 sqlmap 120s 邊緣超時 ×2 → critical 消失（發現根因）
- #16（最終）：**22 findings（2C+3H+9M+5L+3I）**——SQLi critical ×2 穩定重現；
  agent-observed ×3（Admin 端點未授權 high／version 洩漏 medium／500 堆疊
  low，全部帶證據）；agent 25 步 66k tokens
- 報告 #16：17 頁，視覺抽查＋evidence 回填後重產驗證（SQLite/techniques
  文字已進入檢測依據區塊）
- 測試：kali_tools/pipeline＋agent 78 項全過；ruff 全過

**狀態**：本波累計 9 個 commit（d64b618 起），皆在本地未 push（使用者指示
push 最後才要求）。

---

## 追記（第四波：#17→#21，登入態重放與 IDOR 自主發現）

**變更**（5 個 commit）：
- replay_request(url, method, body, store_token_key)：帶 agent session
  （localStorage token＋context cookies）重放同源請求；登入回應 token 寫回
  localStorage 形成認證閉環；method 限 GET/POST；JWT 於 snippet 壓縮為
  [JWT len=N]（省 context 且讓 bid 等欄位可見）
- SECURITY_FIRST_PROMPT：優先 API 註冊登入（不操作 UI 表單）、寫入測試
  先取自有資源 id——方法論引導
- demo：AGENT_MAX_STEPS 40→64、TOKENS 250k→320k

**迭代實錄**（每輪診斷→修正）：
- #17：agent 自主完成 UI 註冊（15 步）但 40 步耗盡在登入表單
- #18：mat-select 泥沼（58 步 329k 爆）→ 改設計：API 註冊登入
- #19：API 註冊登入 4 步閉環；但 token 抽取用截斷 snippet parse 失敗
  （JWT 700+ 字元 > 400 上限）→ 修為完整回應 parse
- #20：**IDOR 自主發現 ×2**（basket 跨帳號讀＋Users 全站列舉，皆 high）、
  **JWT 內含 password hash（agent 超越預期的自主發現）**；負數差 bid
- #21：23 findings 穩定重現；負數仍差自有 bid 推導（quantity=-100 重放
  被 Invalid BasketId 擋）——原語手動驗證可寫入，agent 推導待精進

**最終格局（#21，23 findings：1C+4H+9M+6L+3I）**：對手 12 項中，
SQLi（工具確認 critical）、跨帳號讀取（IDOR ×2）、未授權存取 ×3、
目錄列表、metrics、CSP、CORS、資訊 headers 全部覆蓋；另獨有 JWT 洢漏、
錯誤頁 ×3、傳輸/DNS 層 ×4、UX/SEO ×7。報告 17 頁（ARGUS-21 編號）。
