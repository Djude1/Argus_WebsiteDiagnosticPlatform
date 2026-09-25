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

---

## 追記（第五波：#22 黑箱最終驗證）

**作弊稽核**（使用者要求的黑箱標準）：
- 記憶：agent `_messages` 每次 run 重建、AgentSession 每掃描新建、provider 無狀態——零跨掃描記憶
- 情報輸入＝全部當次觀察：crawler XHR 攔截（本掃描流量）、network log（agent 本 session）、replay 即時回應
- 環境層（非 agent 輸入）：VerifiedDomain admin override、demo 帳號——與 agent 無關
- 移除兩處 prompt 殘留的「如 /rest/、/api/」路徑例子（commit 黑箱稽核）——至此 prompt 僅含方法論與工具描述

**#22 結果（黑箱）**：22 findings 全部重現（SQLi critical、IDOR、Users 全站
列舉、Admin config 未授權、目錄列表、metrics、指紋 headers）——無路徑提示
下 agent 自主找到同樣漏洞，黑箱成立。

**負數（business logic）**：agent 步驟 54-56 完整重現——探索自有 basket 11
→ POST quantity=-100（200，寫入）→ GET basket/11 驗證內容已變（529 bytes、
Products 已填充）——**已重現且自行驗證**，僅 report 動作被 token 上限
（331k>320k）截斷；完整軌跡存 AgentStep（scan 22 steps 54-56）。

**最終格局**：對手 12 項全部有對應偵測（其中 SQLi/IDOR/未授權/負數為
agent 或工具主動重現），另獨有 JWT 洩漏（#20/#21）、錯誤頁洩漏、
傳輸/DNS/UX/SEO 維度與報告防偽。

---

## 追記（第六波：多 session 分工與寫入型 IDOR）

**變更**：
- deep_mode 改雙 session 分工（RECON_AGENT_PROMPT／AUTH_AGENT_PROMPT，
  pentest-ai-agents role 化概念）：獨立 browser context 與 LLM messages、
  序列執行、_merge 合併（findings 串聯＋persist 去重）
- replay_request method 加 PUT/PATCH（寫入型 IDOR 的 update 端點）
- Nuclei extra_urls 限帶參數端點前 3 個（#23 全塞 12 URL × 全模板掛死；
  process-tree terminate 對 Go 程序未生效的 kill bug 另案）
- GitHub 直查「對手可能是什麼」：IDOR 工具最高 46★（Burp ext）、business
  logic scanner 零結果、juice-shop 自動解僅 0★ 寫死腳本——「經典專案全自動
  找到 IDOR/負數」不成立；結論寫入 competitive-positioning.md

**#24 結果（雙 session，22 findings：2C+5H+9M+3L+3I）**：
- **寫入型 IDOR（high）自主發現**——POST /api/BasketItems/ 不帶 BasketId 時
  寫入任意既有 basket（證據：自己無 basket → 無 id POST → 200 建立在
  他人 basket）＝對手「跨帳號修改他人購物車」的全自動重現
- 讀取型 IDOR ×2（basket＋Users 含管理員）穩定重現
- auth role 56 步耗盡於 IDOR 探索，負數未測（#22 軌跡為證）；登入繞過
  payload 未觸發（列為待補）

**漏洞級對打終局**：Argus 11 項（SQLi×2＋讀取 IDOR×2＋寫入 IDOR＋admin
config＋ftp×2＋metrics＋security.txt＋recruiting）vs 對手 10 項——黑箱、
全自動、每項帶證據；負數另以 #22 軌跡佐證。

---

## 追記（第七波：指揮官 subagent 模式定稿——#26/#27）

**變更**（4 commit）：
- 真·subagent：dispatch_specialist tool（指揮官 session 內派工、結果即時回流、
  可多輪追加）；specialist 不帶 dispatch（防遞迴）
- specialist 角色目錄 3→5（auth_idor/injection/logic_abuse＋新 info_leak、
  jwt_token_abuse），每角色帶 desc＋when；dispatch schema 的 role enum 由
  目錄動態生成——指揮官「知道手中有什麼、何時用」（hermes-agent 能力
  目錄化＋pentest-ai-agents when-to-use 慣例）
- 四 repo 查證結論進 research 文件（strix 獨立 CLI 不適嵌入、shannon
  AGPL＋需源碼、pentest-ai-agents 是 prompt 集非 runtime、Scanners-Box
  選型參考）；架構決策＝runtime 自研＋知識層借鑑

**#26（外層編排三 role 對照）**：25 findings（1C+8H）——inject role 首航
即中**登入 SQLi 繞過**（' OR 1=1-- 取得 JWT，×2 high）＋負數進 findings
（與寫入 IDOR 合併）＋CAPTCHA 自答漏洞。對手 12 項全覆蓋。

**#27（subagent 指揮官模式）**：**31 findings（1C+8H+13M）歷史新高**。
session 证据：recon(22步)→orchestrator(11步內 dispatch×10)→10 個
specialist session。新命中：負數獨立 high、search SQLi 完整 UNION
資料庫傾印（Users 表）、/api/Challenges 64KB 漏洞地圖未授權、
SecurityQuestions/Feedbacks email hints 洩漏、Express 錯誤路徑 ×2。

**調校項（誠實）**：orchestrator 每角色派 2 輪（共 10 specialist），
總 token ~165 萬/掃描——需在 prompt 收斂（例如「同角色原則上一次」）；
部分 specialist token 爆（320k/個）但全有產出。

**終局對打**：漏洞級（排除組態類）Argus #27 ≈ 14 項 vs 對手 10 項，
涵蓋對手全部類別（SQLi×3、IDOR 讀/寫、負數、ftp、metrics、時間戳近似、
資訊類），另獨有 Challenges 地圖洩漏、CAPTCHA 自答、資料庫傾印證據、
SecurityQuestions/Feedbacks 洩漏——全黑箱、全自動、逐項帶證據。

---

## 追記（第八波：#28 一次定生死——黑箱終局驗證）

**掃前補強**（使用者指示：payload 屬工具論保留；補齊缺工具；加 feedback）：
- 4 新工具：get_page_html／get_storage／get_response_headers／decode_jwt
  （皆通用；storage 值遮罩為長度；jwt 不回傳 token 本體）
- report_security_issue 注入 7-Question Gate 精神（回報前自問兩題）
- DEFAULT_SYSTEM_PROMPT：finish summary 必含「未能完成的測試與原因」；
  tasks.py 以 feedback 鍵寫入 warning_summary['agent']（DB/API only）
- bug-hunter 類 repo 查證（Agentic-Bug-Hunter／Claude-BugHunter）進 research

**黑箱程序**：靶機容器重啟（記憶體 DB 清空、歷次殘留帳號排除）→
agent 全模組作弊稽核（零記憶／零目標特定路徑／payload=工具論）→ 單次掃描。

**#28 結果（24 findings：1C+8H+8M+4L+3I，overall 72）**：
- SQLi critical（sqlmap 四技法）＋登入繞過 high（帶 401 控制組對照）
- IDOR 三態全中：讀取（GET basket）＋修改（PUT BasketItems）＋新增
  （POST 帶他人 basket_id）——比前輪更完整
- 負數 high（獨立落地，寫入持久化為證）
- 組態類＋ftp×2＋metrics＋security.txt＋recruiting
- feedback 機制首航生效：recon 自述 /ftp/quarantine/ 子目錄線索
  （未落地為 finding——機制正確捕獲「發現未報」案例，列下輪修正）

**漏洞級對打終局（#28）**：16 項資安（1-16）vs 對手 12 項；對手全部
類別覆蓋（SQLi×2／IDOR 讀寫／負數／ftp／metrics／CSP／CORS／資訊類），
另獨有寫入 IDOR 兩態＋負數獨立項＋security.txt。全程黑箱、單次、
自動、逐項帶可重現證據。
