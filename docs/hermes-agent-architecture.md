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
         └─ finish（安全網：orchestrator 零派工時全角色補跑）
合併（_merge）→ persist（description 去重）→ 進 scoring
```

序列執行（RPS 與 Kali 預算全域共享）；每角色獨立預算上限
（`ARGUS_AGENT_MAX_TOKENS`；specialist 另受 `_SPECIALIST_MAX_STEPS=60` 步數盒）。

## 2. Specialist 角色目錄（SPECIALIST_ROLES）

| role | 職責 | when（派用時機） |
|---|---|---|
| `auth_idor` | API 註冊登入、跨帳號讀/寫 IDOR（含 PUT/PATCH）；**全程 API 禁 UI** | 登入/註冊端點、帶 id 授權資源 |
| `injection` | 登入繞過 SQLi payload、XSS 反射（**API 優先**） | 登入表單、query 輸入點 |
| `logic_abuse` | 負數/極端值、流程繞過、CAPTCHA/OTP 重用、open redirect；**鐵律＝驗證成功下一個動作就是 report** | 數量/金額欄位、多步流程、驗證碼 |
| `info_leak` | 敏感檔/錯誤頁/中繼資料/debug 端點（只讀） | 可疑路徑、非標準錯誤回應 |
| `xss_hunter` | 反射/DOM/儲存 XSS（query 輸入點、iframe、innerHTML 渲染後檢查） | query 輸入點、HTML 回應端點 |
| `jwt_token_abuse` | JWT payload 敏感欄位（decode_jwt）、簽章/過期竄改重放、cookie 屬性 | token 型登入、Set-Cookie |

authenticated scan：使用者帳密（`test_auth_*_encrypted`，Signer 加密）
自動注入 `auth_idor`／`logic_abuse` prompt——無公開註冊的真實站靠這個。

## 3. 工具清單（ToolExecutor，20 個）

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

**回報/調度**：`report_security_issue`（critical 封頂 high；回報前自問
「攻擊者現在能做到嗎？證據能重現嗎？」）／`report_ux_issue`／
`dispatch_specialist`（僅 orchestrator）／`decode_jwt`（不驗簽）／
`finish`（summary 必含「未能完成的測試與原因」→ `warning_summary.agent.feedback`）

## 4. 迴圈治理（loop.py）

| 機制 | 觸發 | 動作 |
|---|---|---|
| 快照壓縮 | 每輪 | bulky 工具只留最新一份全量（32步260k→36步169k） |
| 空轉導正 | 連續 ≥4 次同型 click/type_text | 注入策略提醒（換方向或 finish） |
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
| `ARGUS_AGENT_MAX_TOKENS` | 60000 | 500000 | 每角色各自上限 |
| `ARGUS_NUCLEI_DEEP_TIMEOUT` | 300 | 900 | pipeline 全模板掃 |
| `ARGUS_KALI_TIMEOUT` | 120 | 240 | sqlmap level3 需 ≥240（120 會邊緣超時） |
| `ARGUS_ALLOW_PRIVATE_TARGETS` | false | true | 私網靶機旁路（DEBUG 雙條件＋scans.E002） |

## 7. 迭代教訓（踩過的坑，勿重蹈）

1. **UI 表單是步數黑洞**（Angular mat-select 讓 agent 耗 38-58 步）——一切優先 API（`replay_request` 直接打註冊/登入端點）
2. **JWT 700+ 字元擠爆 400 字元 snippet**——token 抽取必須 parse 完整回應
3. **nuclei `-lna`＝封鎖私網**（非允許）——私網靶機須旁路時移除
4. **sqlmap 裸 `--batch` 對空值 `?q=` 兩秒誤判**——`--level=3`
5. **單 session 塞全部工作必爆**——角色分工＋各乾淨 context
6. **觀察到 ≠ 落地**——report 紀律（立即報）＋終局提示＋feedback 機制三重保險
7. Express serve-index 目錄列表標題是 `listing directory`（非 Apache `Index of /`）——兩種都要認

## 8. 戰果基準（Juice Shop，黑箱）

四輪聯集（#30/31/33/34）：43/40/51/40 findings；核心類別（SQLi×2、IDOR
讀寫、負數、ftp、metrics、Challenges、email 洩漏）**聯集 100%**；峰值 #33
（51/24H，含 mass-assignment 提權、CAPTCHA 自答）。同口徑 vs 對手 9 項：
領先 11~15。樣本與軌跡：`log_assets_juice/`（未追蹤）。
