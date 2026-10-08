# Hermes-Agent 滲透測試架構（2026-09-26 定稿）

> 對應模組：`backend/apps/agent/`。本文件是 agent 系統的單一事實來源：
> 角色目錄、工具清單、流程、調校參數、迭代教訓。改 agent 前先讀。
> 戰果與迭代全記錄見 `log/2026-09-25_juice-shop-attack-surface.md`。

## 1. 執行流程（deep_mode）

```
ScanJob(active+authorized)
 └─ recon agent（固定首跑）：network log 偵察→SQLi probe(sqlmap)→匿名未授權掃
     └─ orchestrator agent（只掛 dispatch_specialist/finish/report；
        首步 tool_choice 強制派工）
         ├─ dispatch_specialist(role, brief) ──→ specialist subagent ×N
         │    每位：獨立 browser context＋獨立 LLM messages＋步數盒 60
         │    結果摘要即時回 orchestrator → 可追加第二輪
         └─ finish（安全網：orchestrator 零派工時依序補跑前 N 個角色）
合併（_merge）→ persist（description 去重）→ 進 scoring
```

每次掃描最多派工 `ARGUS_AGENT_MAX_SPECIALIST_DISPATCH`（預設 6）次，超過時
`dispatch_specialist` 回 `dispatch_limit_reached`；零派工安全網也只補跑前 N 個角色
（2026-10-07，控制深度資安附加費 50 coin 的成本上限）。

序列執行（RPS 與 Kali 預算全域共享）；每角色獨立預算上限
（`ARGUS_AGENT_MAX_TOKENS`；specialist 另受 `_SPECIALIST_MAX_STEPS=60` 步數盒）。

## 1b. 擬真使用者 UX 測試模式（passive 也跑，2026-09-28）

同一支 `run_agent_for_scan` 的第二種角色，與資安 deep_mode 並存但閘門分離：

```
ScanJob(scope=site 且 categories 含 ux)         # 不需 active/authorized
 └─ run_agent_ux（scan_plan 判定）＋ ARGUS_AGENT_ENABLED
     └─ 單 session（DEFAULT_TASK_PROMPT_TEMPLATE）：像真實使用者操作
        get_dom_summary → 點主要 CTA → 走表單/結帳流程 → report_ux_issue
        → finish
合併 → persist_agent_issues（category=UX finding）→ 進 scoring
```

- **觸發**：`scan_plan.build_scan_execution_plan` 設 `run_agent_ux = scope=="site" and "ux" in effective_categories`；`tasks.py` 以 `run_agent or run_agent_ux` 觸發 agent。單頁不跑（無流程）。
- **表單送出閘門（`may_submit_forms`）**：`tasks.py` 算 `may_submit_forms = run_agent(deep_mode) or user_owns_domain(user, hostname)`，傳入 `run_agent_for_scan`。`runner` 的 passive 分支據此組 `submit_clause`（送出 vs 只填不送）並傳 `_run_session(..., allow_form_submit=...)` → `build_tool_schemas` 在不允許時隱藏 `send_message`。未驗證他站只做「填入示意資料觀察欄位／驗證提示」，不留測試資料。
- **計費**：固定附加費 `ARGUS_COIN_AGENT_UX`（見 billing `agent_ux_fee`），與 `run_agent_ux` 收費條件對齊。
- **與規則式 UX 的分工**：規則式檢查（tap target/未標記欄位/JS 例外，見 `scans/CLAUDE.md`）每頁都跑、不需 LLM，是 UX 的地板；Agent UX 是需要 LLM 的擬真流程測試，兩者都產 `category=UX` finding。

## 2. Specialist 角色目錄（SPECIALIST_ROLES）

| role | 職責 | when（派用時機） |
|---|---|---|
| `auth_idor` | API 註冊登入、跨帳號讀/寫 IDOR（含 PUT/PATCH）、密碼重置鏈帳號接管（WSTG-ATHN-09）；**全程 API 禁 UI** | 登入/註冊/重置端點、帶 id 授權資源 |
| `injection` | 登入繞過 SQLi、XSS 瀏覽器執行驗證（hash 路由）、家族化注入 probe_payload_injection（NoSQL/SSTi/XXE/指令/LFI） | 登入表單、query/JSON/XML 輸入面（SQL 探測≠家族覆蓋） |
| `logic_abuse` | 負數/極端值、流程繞過、CAPTCHA/OTP 重用、open redirect；**鐵律＝驗證成功下一個動作就是 report** | 數量/金額欄位、多步流程、驗證碼 |
| `info_leak` | 敏感檔/錯誤頁/中繼資料/debug 端點（只讀） | 可疑路徑、非標準錯誤回應 |
| `xss_hunter` | 反射/DOM/儲存 XSS（query 輸入點、iframe、innerHTML 渲染後檢查） | query 輸入點、HTML 回應端點 |
| `jwt_token_abuse` | JWT payload 敏感欄位（decode_jwt）、簽章/過期竄改重放、cookie 屬性 | token 型登入、Set-Cookie |
| `file_upload` | 檔案上傳面（WSTG-BUSL-08）：副檔名/content-type/路徑穿越/大小邊界＋上傳後匿名直讀（replay files 參數） | multipart 流量、頁面上傳欄 |
| `crypto` | JWT 偽造（forge_jwt：alg=none/HS256 弱密鑰清單）、簽章接受度四路測試、可預測隨機值 | eyJ token、優惠碼/驗證碼類回應 |

authenticated scan：使用者帳密（`test_auth_*_encrypted`，Signer 加密）
自動注入 `auth_idor`／`logic_abuse` prompt——無公開註冊的真實站靠這個。

## 3. 工具清單（ToolExecutor，26 個；另含離線知識庫）

**觀察（bulky，舊快照自動壓縮）**：`get_dom_summary`／`get_visible_text`／
`get_network_requests`（same-origin XHR/fetch 被動攔截——SPA 端點主要來源）／
`get_page_html`（原始碼：注釋/hidden/inline）／`get_storage`（localStorage 鍵長
＋cookie 屬性，值遮罩）／`take_screenshot`

**主動（deep_only：deep_mode schema 隔離＋runtime 再驗＋同源閘）**：
- `replay_request(url, method∈GET/POST/PUT/PATCH, body, store_token_key?)`——
  帶 session 重放原語（IDOR 三態/mass-assignment/負數全靠它）；
  `store_token_key` 把登入回應 token 寫 localStorage（完整回應 parse，
  snippet 中 JWT 壓縮為 `[JWT len=N]`）
- `probe_sql_injection(url)`→Kali sqlmap（`--level=3`；timeout 需 ≥240s）
- `probe_unauthorized_access(url)`——無憑證匿名重放
- `run_nuclei(url, tags?)`——agent 自主模板快掃（120s；與 pipeline 900s 全掃互補）
- `navigate_and_observe(url)`——**執行層觀察閉環**（XSS 金證據）：同源 goto→
  dialog 監聽（alert/confirm/prompt＝JS 已執行）＋console＋渲染後 DOM/可見文字。
  誕生原因：#33/#34 XSS specialist 各 63/62 步 replay_request 0 發現——SPA 的
  HTTP 回應是空殼，「回應含 payload」永遠不成立；XSS 判定必須回到瀏覽器執行。
  邊界：runtime 同源再驗＋deep_mode 再驗（context route 主文件攔截仍是第一層）
- `probe_payload_injection(url, family∈nosql/ssti/xxe/command/lfi, method, query_param?/
  body+inject_field?)`——**家族化注入探測**（SQL 以外）：一次跑整組無害 payload
  （$gt/$ne/$where、{{7*7}} 四型、XXE ENTITY、;echo 標記、路徑穿越 passwd），先打
  baseline——marker 需「payload 回應出現且 baseline 不出現」才算命中（消回應本含
  49/root: 雜訊）；帶登入態（與 replay 同憑證源）。誕生原因：#33/#34 ssti/xxe 0
  觸碰、nosql 1-2 次觸碰——SQL probe 之外的注入面完全沒有探測原語。

- `send_message(text, selector?)`——UI 互動原子化：自動偵測可見輸入框→
  fill→Enter（無新請求則 fallback 送出鈕）→回傳 network log 增量＋回應
  文字尾段。誕生原因：#46/47 type_text 填了沒按送出→真 API 進不了流量
  →猜端點 14 次全錯。chat/對話/搜尋送出場景第一步。
  **`allow_form_submit=False`（未驗證網域的 passive UX 測試）時此工具被隱藏**，
  agent 只能填欄位不能送出（見 §1b 表單送出閘門）。
- `collect_target_intel(target, urls≤8)`——帳號接管情報彙整（WSTG-ATHN-09
  檢索化）：帶憑證 GET×N、全文搜目標（email＋前綴）、命中抽前後 250 字
  上下文（≤15 片段）。誕生原因：#48 agent 讀了備份檔但答案線索被 context
  淹沒。**注意：M3 三路引導×三輪 0 採用（見已知限制）——工具正確但模型
  不叫；換更強模型時採用率為第一測點**

**知識（全域，passive 也可用）**：`search_knowledge(query)`——離線方法論知識庫
（`backend/apps/agent/knowledge/*.md`，15 檔 61 段：WSTG/PayloadsAllTheThings/
jwt_tool 通用方法論摘錄＋reverse-skill 蒸餾四檔——密碼重置答案推理、CSP 繞過、
JWT kid/jku、$regex 盲注、優惠碼規律、上傳 polyglot、SSRF 無 OOB、備份殘留、
站內 OSINT、CAPTCHA 缺陷、注入家族判定、GraphQL、WebSocket、限速繞過、
LLM/chatbot 注入）；關鍵詞評分（tags×3＋標題×2＋內文）回 top 3 段落。設計依據：
Excalibur 檢索增強知識；網路搜尋裁定不做（黑箱抄答案＋目標外洩）。

**回報/調度**：`report_security_issue`（2026-09-28 起封頂 medium、附判定依據與 IP 核對；回報前自問
「攻擊者現在能做到嗎？證據能重現嗎？」）／`report_ux_issue`／
`dispatch_specialist`（僅 orchestrator）／`decode_jwt`（不驗簽）／
`finish`（summary 必含「未能完成的測試與原因」→ `warning_summary.agent.feedback`）

## 4. 迴圈治理（loop.py）

| 機制 | 觸發 | 動作 |
|---|---|---|
| 快照壓縮 | 每輪 | bulky 工具只留最新一份全量（32步260k→36步169k） |
| 空轉導正 | 連續 ≥4 次同型 click/type_text | 注入策略提醒（換方向或 finish） |
| 假設與換道 | system prompt＋dispatcher 尾巴（所有 specialist） | 行動前寫假設/驗證/放棄條件；同手法 3 次無新資訊＝列未試假設換道；先交叉比對既有觀察再發新請求（Excalibur 2602.17622 TDA；#33/#34 實證 77 次觸碰未成鏈） |
| 終局收斂 | 剩 10 步 | 注入「停止探索、立即 report 未報發現」（#30~#32 教訓：未回報＝遺失） |
| 首步強制 | orchestrator | `tool_choice` 鎖定 dispatch_specialist（根除讀完情報直接文字收尾） |
| 步數盒 | specialist | `_SPECIALIST_MAX_STEPS=60`（token 上限加多大都會爆，收斂才是解） |
| 速率紀律 | system prompt | 429/連續 403 → 停打改測其他（真實站 WAF） |

## 5. 模型鏈

MiniMax-**M3**（2026-06；同價同 API；SWE-bench 80.5）→ GLM → Gemini（純文字）。
M3 特性：思考型、探索深（步數上限會切斷）、行為非決定性（跨輪 findings
波動 ~20%——核心類別聯集 100%，比賽呈現建議多輪聯集）。
後續候選：Qwen3.8 Max／Kimi K3／DeepSeek V4.1 Flash（需新 key，產品決策）。

## 6. 調校參數

| 參數 | 正式預設 | demo（juice yml） | 說明 |
|---|---|---|---|
| `ARGUS_AGENT_ENABLED` | false | true | 總開關 |
| `ARGUS_AGENT_MAX_STEPS` | 20 | 100 | orchestrator/recon 用；specialist 另受 60 盒 |
| `ARGUS_AGENT_MAX_TOKENS` | 60000 | 500000 | 每角色各自上限；**chat 場景 500k 不足**（回應全文進 context，#53-55 實測 900k 三 specialist 仍爆至 908-938k）——chat 導向輪建議 exec 進程同步 apply 覆寫（Celery 常駐進程不吃 exec env） |
| `ARGUS_NUCLEI_TIMEOUT` | 660 | 900 | pipeline Nuclei（KEV 模板集、只掃網站根網址；2026-10-08 前為 `ARGUS_NUCLEI_DEEP_TIMEOUT` 全模板） |
| `ARGUS_KALI_TIMEOUT` | 120 | 240 | sqlmap level3 需 ≥240（120 會邊緣超時） |
| `ARGUS_ALLOW_PRIVATE_TARGETS` | false | true | 私網靶機旁路（DEBUG 雙條件＋scans.E002） |

## 7. 迭代教訓（踩過的坑，勿重蹈）

1. **UI 表單是步數黑洞**（Angular mat-select 讓 agent 耗 38-58 步）——一切優先 API（`replay_request` 直接打註冊/登入端點）
2. **JWT 700+ 字元擠爆 400 字元 snippet**——token 抽取必須 parse 完整回應
3. **nuclei `-lna`＝封鎖私網**（非允許）——私網靶機須旁路時移除
4. **sqlmap 裸 `--batch` 對空值 `?q=` 兩秒誤判**——`--level=3`
5. **單 session 塞全部工作必爆**——角色分工＋各乾淨 context
6. **觀察到 ≠ 落地**——report 紀律（立即報）＋終局提示＋feedback 機制三重保險
7. **工具進 schema ≠ 角色會用**——新工具需同步改角色提示詞與 `when` 能力目錄
   （P0-3 prober 連兩輪 0 呼叫才打通：injection 提示詞＋when「家族只有此角色能測」）
8. **SPA 驗證打前端路由不打 API URL**——API 回 JSON 不渲染；`/#/` hash 路由
   才是執行現場（XSS 35 輪全滅的另一半根因）
7. Express serve-index 目錄列表標題是 `listing directory`（非 Apache `Index of /`）——兩種都要認
9. **新工具採用有梯度**——navigate（首輪）、forge_jwt（兩輪）、prober（三輪＋
   when+prompt 雙補）；但 collect_target_intel 三路引導（定向明列/5b 深位/
   第一步高位）×三輪全 0——**觸發條件在情報中不顯眼的工具，M3 不會採用**，
   工程不可解（模型行為層）
10. **XSS 偵測掛載體差異**——事件屬性類（img onerror）與 URL 載入類
    （iframe javascript:）觸發路徑不同，站方偵測常只覆蓋一類——雙載體
    都測（手動 Playwright 對照實證後寫通用紀律）
11. **Celery 常駐進程不吃 exec env**——settings 覆寫必須 `run_scan_job.apply`
    同步執行才生效；靶機 restart 後必輪詢就緒（version 200）才建掃描
    （#45 爬蟲零頁教訓）

## 8. 戰果基準（Juice Shop，黑箱）

**競賽期**（#30/31/33/34 四輪聯集）：43/40/51/40 findings；核心類別聯集
100%；峰值 #33（51/24H）。同口徑 vs 對手 9 項：領先 11~15。

**內部提升期**（#35-55，21 輪＋8 定向）：解鎖 22→**26/112**（記分板
`docker logs Solved` 事件為 ground truth——`/api/challenges` solvedAt 勿信）。
四個類別首穿：`resetPasswordJimChallenge`（帳號接管全鏈）、
`localXssChallenge`（DOM XSS 雙載體）、`freeDeluxeChallenge`（商業邏輯深水）、
`uploadTypeChallenge`（上傳面）。900k 全掃單輪峰值 12 種重解＋38 findings
（穩定性大幅提升）。26 種＝M3 當前架構穩定重現集。

## 9. 已知限制（2026-09-28 定案：M3 行為層，工程不可解）

22 全掃＋8 定向（M3 500k/900k＋GLM 各試）全組合窮盡，26/112 為「便宜模型
最低成本」策略的真實高原：

1. **工具採用極限**：`collect_target_intel` 三路引導×三輪 0 呼叫——auth
   角色注意力在註冊/IDOR 本業，reset 條件子項（5.x）被跳過；與 prober
   （when 補描述即上）差異＝觸發條件顯眼度。換更強模型時此工具採用率
   為第一測點
2. **Chatbot 簇（3 挑戰）**：chat 鏈前三環已穿（真端點 /rest/chat、對話
   18 發 200、900k 盒下 v3 走通全鏈＋chat 領域首件 report），第四環＝
   Juice Shop 特定判定條件，超出 OWASP LLM 通用方法論——深入即目標
   特定＝黑箱紅線禁區
3. **reset 語義推理**：Bender/Bjoern 答案需「備份檔內容→題型」跳躍——
   M3 推理深度邊際（Jim 已穿＝能力在，邊際不在方法論）
4. **指令遵循**：步數預算指示被無視（chat 定向「12 步」兩輪實證）；
   orchestrator 派工波動（覆蓋紀律提示詞入檔後仍偶發跳角色）
5. **自進化記憶**：裁定分階段——現階段黑箱測底不做；最後階段加案例庫
   （掃後離線寫入知識庫、掃前檢索注入；記方法論結晶禁 writeup）
