# Juice Shop 缺口分析（內部提升循環起點）

**日期**：2026-09-26
**資料來源**：demo DB ScanJob #30/31/33/34 findings 聯集、AgentStep 725 步行為統計、Juice Shop v20.0.0 完整挑戰清單（112 項）
**背景**：競賽對抗已結束（領先對手 10-15 項），本分析供內部能力提升。

## 覆蓋現況

112 挑戰中，agent 五輪聯集等效覆蓋約 **12-14 項（~11%）**：

| 已覆蓋挑戰 | 證據（聯集 finding） |
|---|---|
| Login Admin | SQLi login bypass（全輪）+ sqlmap crit 驗證 |
| View Basket | IDOR /rest/basket/{id} |
| Manipulate Basket | Write-IDOR checkout / PUT BasketItems |
| Payback Time | negative quantity -9999 |
| Product Tampering | PUT /api/Products 覆寫任意商品（#30） |
| Confidential Document | /ftp 目錄列表 |
| Exposed Metrics | /metrics 未授權 |
| CAPTCHA Bypass | /rest/captcha/ 回應自帶答案（#33） |
| Admin Registration | POST /api/Users role=admin 提權（#33） |
| Password Hash Leak | JWT payload 含 bcrypt 雜湊 |
| Error Handling | verbose error 多輪（部分等效） |
| Login Bender/Jim | SQLi 能力等同（僅示範 admin，半算） |

## 未覆蓋 98 項按根因分組

### A. XSS 家族（9 項）——方法論錯配（最嚴重）
DOM XSS、Reflected XSS、API-only XSS、HTTP-Header XSS、CSP Bypass、Client-side XSS Protection、Server-side XSS Protection、Video XSS、Bonus Payload

**實證**：#33 XSS specialist 63 步、replay_request 54 次、report **0 次**；#34 62 步、report **0 次**。
**根因**：
1. 提示詞設計「全程 API 優先，不操作 UI」——但 Juice Shop XSS 全在 client 端 Angular 渲染，replay_request 收到的永遠是 SPA 空殼 index.html，探測字串永遠「不出現在回應中」→ 永遠判定安全 → 0 report。
2. 無執行閉環工具：XSS 金標準＝導航後 JS 真正執行的副作用（dialog/alert、DOM 變更、console、外部回調）。現有 Playwright 工具（click/get_page_html）可行但提示詞明確引導離開 UI；且無「等 dialog」「比對前後 DOM diff」工具。

### B. 密碼重置/帳號接管鏈（8 項）——多步鏈走不完
Reset Jim/Bender/Bjoern/Morty/Uvogin ×5、Change Bender's Password、Bjoern's Favorite Pet、Two Factor Authentication

**實證**：SecurityQuestion 端點被觸碰 77/43 次（auth 角色反覆讀清單），/rest/user/reset 5/16 次，但從未走到「提交答案→收 token→重設→登入驗證」完整鏈。
**根因**：鏈長（4-5 步 API 呼叫＋答案來源推理）超過 specialist 單一注意力；部分答案需 OSINT（Geo Stalking、寵物名）黑箱內無網搜工具（合理不計）；但 Jim/Bender 答案可從洩漏資料推（user credentials、留言）。

### C. 注入進階（8 項）——payload 光譜不足
NoSQL DoS/Exfiltration/Manipulation、SSTi、XXE ×2、User Credentials、Ephemeral Accountant、Christmas Special、Chatbot Prompt Injection ×2、Greedy Chatbot

**實證**：nosql 觸碰 1/2 次、ssti 0、xxe 0、chat 53/19 次（碰到沒打穿）。
**根因**：probe_sql_injection 只認 SQL 語法；無 generic payload prober（NoSQL `$gt`/`$where`、SSTi `{{7*7}}`/`${7*7}`、XXE DOCTYPE）。Chatbot 是 LLM prompt injection——全新攻擊面，無角色覆蓋。

### D. 檔案上傳/路徑（6 項）——工具缺口
Upload Size/Type、Arbitrary File Write、Local File Read、Misplaced Signature File、Access Log、Leaked Access Logs

**根因**：replay_request 無 multipart 能力；無路徑穿越/副檔名黑名單繞過 probe；B2B 檔案（profile.zip）鏈路完全未探索。

### E. 密碼學/偽造（8 項）——角色缺口
Forged Coupon、Premium Paywall、Weird Crypto、Nested Easter Egg、Imaginary Challenge、Forged Signed JWT、Unsigned JWT、Steganography

**根因**：無 crypto specialist；decode_jwt 只有解碼無偽造（alg:none、弱 HMAC 爆破）；coupon 是 HMAC 偽造需離線計算。

### F. 商業邏輯深水（10 項）——劇本深度不足
Expired Coupon、Deluxe Fraud、Wallet Depletion、Multiple Likes、Five-Star Feedback、Zero Stars、Forged Feedback/Review、Repetitive/Empty Registration

**實證**：coupon 觸碰 1/21 次、deluxe 14/11、wallet 11/6——碰到沒打穿。
**根因**：logic_abuse 角色有但提示詞只有通用原則（負數、重放），每個挑戰需特定玩法（時序窗口、欄位濫用、狀態機跳步）。

### G. 元件/供應鏈（6 項）——無依賴分析
Vulnerable Library、Frontend/Legacy Typosquatting、Supply Chain Attack、Cross-Site Imaging、Deprecated Interface

**根因**：無前端 npm 依賴稽核工具（node_modules 掃描、sourcemap 分析）。

### H. Out-of-band 依賴（4 項）——基礎設施缺口
SSRF、Blocked/Successful RCE DoS、Memory Bomb

**根因**：無 OOB callback 基礎設施（自建 webhook listener／interact.sh 類）；SSRF 需觀察目標對外部 URL 的出站請求。

### I. Web3（4 項）——ROI 低不投資
Blockchain Hype、NFT Takeover、Mint the Honey Pot、Web3 Sandbox

### J. 雜項不適用
Score Board、Privacy Policy 等（人類玩法/文件類）。

## 行為統計摘要（#33/#34，725 步）

| 訊號 | #33 | #34 | 解讀 |
|---|---|---|---|
| XSS specialist report 次數 | 0/63 步 | 0/62 步 | 白跑兩輪——方法論＋紀律雙失效 |
| replay_request 佔比 | 最高 71/85 | 最高 58/73 | 全系統性偏向 HTTP client，遠離瀏覽器 |
| JWT specialist 步數 | 16+10 | — | 自願早退（tokens 還剩）——提示詞任務定義太窄 |
| 攻擊面觸碰率 | chat 53、SecQ 77、coupon 1 | chat 19、SecQ 43、coupon 21 | 「碰到沒打穿」是主模式 |

## 外部研究佐證（2026-09-26 查證）

### 案例一：CAI（aliasrobotics/cai，9.8k★，已封存轉 CSI）
- **架構**：bug_bounty agent 核心工具＝`generic_linux_command`（通用 shell，agent 自己組合 nmap/nuclei/sqlmap/curl/ffuf）＋`search_web`＋`Todo_list`（計畫追蹤）＋shodan；角色化 agents（redteam/bug_bounty/dfir/network…）
- **方法論**（system prompt 實文）：ReAct（plan→act→observe→adapt）＋ TRACE loop（每步：假設→單一有界限測試→證據→驗證→下一步）＋ **Decision Log 每步一行** ＋ **「breadth before depth」**（先廣度覆蓋再深挖）
- **成績**：CTF 41/45 flags、Dragos OT CTF 32/34（1000 隊中 48 小時第 7-8 小時登頂）、宣稱 3600× 快於人類；「Jeopardy CTFs are now a solved game」

### 案例二：Excalibur（arXiv:2602.17622，2026/02）——最直接回答「需要什麼條件」
分析 28 個 LLM 滲透系統＋實測 5 個代表實作：
- **核心結論**：模型 scaling 解決不了的瓶頸＝「缺乏任務難度即時估算」→努力分配錯誤、過度投入低價值分支、**在完成攻擊鏈前耗盡 context**
- **失敗分類**：Type A（工具/prompt 缺口，工程可解）vs Type B（規劃與狀態管理缺陷，換模型沒用）
- **有效條件**：型別化工具層＋TDA（四維難度估算：horizon/evidence confidence/context load/historical success）＋EGATS（證據引導攻擊樹搜尋，exploration-exploitation 切換）
- **成績**：CTF 91% 完成率（+39-49%）、GOAD 5 台陷 4 台（前系統 2 台）

### 案例三：能力追蹤研究（arXiv:2609.10780，2026/09）
- **記憶假說被否定**：加 coverage-memory 層，兩套系統皆無改善
- **真正瓶頸＝規劃**：失敗運行中 agent「held the evidence for a route forward」卻未形成攻擊假設
- 建議：投資規劃能力，不投資長程記憶

### 案例四：XBOW（商業標竿）
- 攻擊鏈串接（多漏洞組合成可利用路徑）＋**回報前獨立驗證可利用性**＋完整決策/戰術日誌
- 2025/6 HackerOne 美榜第一（自主系統首例）、MSRC 首個上榜自主系統、宣稱 14,000+ 零日（不可驗證）

### 案例五：其他
- PentestGPT（USENIX Security '24）：LLM 核心限制＝失去整體情境理解（context loss）；task completion +228.6%
- CHECKMATE（2512.11143）：古典規劃＋LLM，勝率 +20% 成本減半
- 攻擊樹引導（2509.07939）：MITRE ATT&CK 結構化推理，子任務完成 71.8-78.6%
- CTF-ABACUS（2608.26237）：1,435 次 CTF 嘗試僅 62-87% 旗幟靠真實漏洞——佐證我們黑箱防作弊稽核的必要性

### 本地實證與文獻的精確對照

| 我們的實證 | 文獻對應 |
|---|---|
| SecurityQuestion 觸碰 77 次未形成「洩漏資料→推答案→重置」假設 | 2609.10780 原句「手握證據未形成攻擊假設」 |
| XSS specialist 63 步全押錯誤方法（replay_request） | Excalibur Type A 工具錯配＋「過度投入低價值分支」 |
| JWT specialist 16 步自願早退（token 剩餘） | Excalibur「努力分配錯誤」 |
| recon→6 角色各自 60 步深挖 | 缺 CAI「breadth before depth」＋TDA 換道機制 |

## 提升方向（外部研究合併後定稿）

**結論：最大投資報酬不在「更多角色/插件」，在規劃層（攻擊假設生成＋難度感知換道）＋XSS 執行閉環。**

### P0（解最大缺口，工程明確）
1. **XSS 執行閉環工具** `navigate_and_observe`：Playwright goto（含 payload URL）→ dialog 事件監聽 → 前後 DOM diff → console 訊息；XSS 提示詞改「瀏覽器執行驗證優先、replay 僅找輸入點」。解 A 組 9 挑戰＋真實世界 XSS 價值最高。根因＝現有 20 工具無 navigate、提示詞明令「不操作 UI」、httpx 收 SPA 空殼。
2. **攻擊假設生成＋換道紀律（規劃層，Excalibur TDA 簡版）**：dispatcher brief 改假設模板（觀察→假設→驗證步驟→**放棄條件**）；loop.py 提示注入「連續 N 次工具結果無新資訊＝列假設清單換下一條，勿重試同方法」。解 B/F 組「觸碰 77 次打不穿」。
3. **Generic payload prober** `probe_payload_injection(family)`：nosql（$gt/$ne/$where）、ssti（{{7*7}}/${7*7}）、xxe（DOCTYPE）、command（;id）家族化無害探測。解 C 組 8 挑戰。

### P1（角色/工具擴充，解 Type A 缺口）
4. **auth 角色擴充 reset-chain 劇本**：枚舉安全問題→交叉比對已洩漏 PII（留言/email/備份檔）→推答案→重置→登入驗證→report。解 B 組 5 挑戰。
5. **replay_request 支援 multipart**（files 參數）＋副檔名/大小邊界測試劇本。解 D 組。
6. **crypto specialist**：decode_jwt 擴充 alg:none 重簽＋弱 HMAC 字典驗證。解 E 組。
7. **Breadth-first 覆蓋紀律**（CAI）：每個輸入點先過完整 payload 矩陣一遍再深挖任一點。

### P2（基礎設施/亮點）
8. **OOB callback 容器**（demo compose 加 listener＋`get_oob_hits` 工具）：SSRF/blind 類。
9. **LLM injection specialist**（chatbot prompt injection）：Juice Shop v20 有 3 挑戰，2026 現實攻擊面、比賽亮點。
10. **Decision Log 結構化**：AgentStep.thought_summary 引導格式（假設/證據/決策一行）——供事後軌跡審計（CTF-ABACUS 啟示）。

### 不投資
- 通用 shell 工具（CAI 模式）：破壞黑箱安全邊界（demo worker 容器無隔離）、專題平台風險不對稱
- Web3 組（4 挑戰）：現實網站罕見
- 長程記憶/跨掃描學習：2609.10780 實證無效＋違反黑箱鐵律

## 追記（2026-09-28 使用者裁定）：自進化記憶機制＝分階段導入

- **現階段（測底能力）**：不做——黑箱乾淨基準優先（跨掃描記憶會污染
  「agent 面對未知環境」的量測；arXiv:2609.10780 記憶層無增益實證亦支持
  底能力與記憶分離評估）
- **最後階段（能力擴增）**：加入——讓 agent 見識並記錄發現過的問題
  （field-journal 式案例庫：目標特徵→有效手法→證據結構），下次面對
  同類網站直接召回。參考 reverse-skill field-journal 機制（當時因黑箱
  紅線排除，現降級為分階段而非永久排除）
- 設計要點（未來實作）：記錄屬「平台資產」非「session 記憶」——
  掃後離線寫入知識庫（knowledge/*.md 擴充或獨立 cases/），掃前檢索
  注入；仍禁目標特定答案（記方法論結晶不記 writeup）
