# Argus 競爭定位與實證方法論（2026-09）

> 用途：回答「你們憑什麼說自己的弱掃專題比別人好？」——用 OWASP Juice Shop
> 靶機的實測數據與產品架構事實回應，不靠形容詞。資料來源：本 repo 程式碼、
> `log/2026-09-25_juice-shop-local-testenv.md` 掃描實錄。

---

## 1. 對手是什麼模式，上限在哪

對手自述：整合 GitHub 經典資安專案、刪除重複功能，做 VAPT（弱掃＋滲透測試）。
這是「**工具編排器（orchestrator）**」模式——本質是 DefectDojo 的簡化版：
價值在整合，偵測能力天花板＝被整合工具的聯集。

這個模式的固有上限（不是做不好，是模式本身決定）：

| 上限 | 原因 |
|---|---|
| 偵測結果無二次驗證 | 工具輸出直接進報告；誤報靠人工 triage |
| 無跨維度結論 | 工具彼此獨立，沒有「這個漏洞對這個網站的生意影響」的整合判斷 |
| 授權與合規是紙上聲明 | 沒有技術性網域所有權驗證，主動掃描的授權依據只是勾選框 |
| 交付物＝工具報告拼接 | 沒有單一結論、沒有防偽機制、沒有計費與產品化流程 |

## 2. 「你們跟 DefectDojo 差異是什麼」（直接回答）

| 面向 | DefectDojo | Argus |
|---|---|---|
| 本質 | **漏洞管理平台**（AST tracking）：本身不掃描，吃 200+ 掃描器報告做 dedup／triage／趨勢 | **自研掃描引擎＋交付平台**一體：從爬蟲到結論到自己手上 |
| 爬蟲 | 無（依賴外部工具） | 自研 Playwright BFS 爬蟲（JS 渲染、行動版量測、截圖、llms.txt/robots 感知） |
| AI | 無內建（2.x 有實驗性） | Hermes-Agent：LLM tool-calling 在真實瀏覽器裡動態操作 UI、驗證 SQLi（三層授權閘＋Kali 隔離執行） |
| 維度 | 只有資安 | 資安＋SEO＋AEO＋GEO＋UX 五維同一份結論 |
| 授權合規 | 不涉（工具自己管） | 宣告式勾選＋**技術性網域所有權驗證**（DNS TXT／meta／檔案三選一＋TTL＋admin override 稽核）雙閘門 |
| 報告 | 模板匯出 | 資料層／排版層分離、防偽編號（HMAC）＋內容 SHA-256 指紋＋公開查驗端點 `/api/verify/<編號>/` |
| 產品化 | 開源 self-host 給資安團隊 | 多使用者、點數計費（冪等 hold/settle/refund）、訂閱、後台稽核 |

一句話版本：**DefectDojo 管理漏洞資產、給資安團隊用；Argus 生產並交付網站診斷結論、
給網站主用。**對手的「整合經典工具」等於同時放棄了引擎自研與交付產品化兩端。

## 3. 「這就是弱掃？還是你們講的弱掃不同？」——用 Juice Shop 實證

不做口頭比較，用同一個國際標準靶機對打：

- **靶機**：OWASP Juice Shop（OWASP 官方維護、故意佈滿漏洞的電商 SPA，
  100+ challenges 涵蓋 OWASP Top 10 全類別）。
- **環境**：本機 Docker 完整堆疊（PostgreSQL＋Redis＋Celery worker＋Playwright＋
  Nuclei v3.8.0＋Katana v1.1.2），功能面與 K8s 正式環境一致
  （Hermes-Agent 開啟、Kali disabled）——見 `docker-compose.juice.yml`。
- **量測指標**（雙方各自掃同一靶機後比較）：
  1. **偵測覆蓋**：命中 Juice Shop 已知漏洞類別數（對其官方 challenge 清單）
  2. **誤報率**：findings 中「靶機實際不存在」的比例
  3. **自主性**：從送出 URL 到結論，需要多少人為介入（Argus：零）
  4. **交付物**：報告完整性、可轉寄性、可驗證性（防偽指紋）

### 本地實測紀錄（2026-09-25，掃描 #9→#21 迭代）

同一靶機（`http://juice-shop:3000`，active＋authorized、全網站、max_pages=15），
Docker 完整堆疊＝K8s 正式功能面（Agent 開啟）＋demo 攻擊鏈（Kali docker backend）。

| 指標 | #11 | #14 | #16 | **#20/#21（最終）** |
|---|---|---|---|---|
| findings | 16 | 18 | 22 | **23（1C+4~5H+8~9M）** |
| 應用層攻擊命中 | 0 | SQLi＋列表＋metrics | ＋未授權×3＋指紋 | **＋IDOR ×2＋JWT 洩漏 hash＋錯誤頁 ×3** |
| Agent 能力 | 20 步 3 UX | 36 步反空轉 | 25 步帶證據回報 | **API 自註冊登入＋帶憑證重放＋IDOR 自主判定** |

**#20/#21 的里程碑**（`replay_request` 登入態重放原語，commit 鏈見 log）：

1. **跨帳號 IDOR 自主發現（high ×2）**：agent API 自註冊（POST /api/Users）→
   API 登入（token 寫入 localStorage）→ 改 id 重放 `/rest/basket/{1,2}`（admin
   與 jim 的購物車）→ 200 帶他人資料 → 正確回報 IDOR——**對手的核心項目
   「跨帳號讀取購物車」以全自動方式重現**；另中 `/api/Users/:id` 全站帳號
   列舉（含所有人 email）
2. **agent 超越預期的發現（high）**：登入回應的 **JWT payload 內含 password
   hash**——非任何人提示、agent 自主從回應內容判斷的真實漏洞
3. 負數數量（business logic）：agent 已執行 `quantity=-100` 重放但用錯
   自有 basket id 被擋——原語與工具皆就緒（手動驗證 200 可寫入），
   agent 的自有資源 id 推導待精進（誠實記錄）

**#21 偵測清單 vs 對手 12 項**（同靶機直接對打）：

| 類別 | 對手（經典工具整合） | Argus #21 |
|---|---|---|
| SQL injection | 已重現 ×2 | **sqlmap 工具確認**（critical，四技法證據鏈） |
| 存取控制：跨帳號讀取 | 已重現 | **IDOR ×2 自主發現**（basket＋全站帳號列舉） |
| 存取控制：未授權存取 | 部分未確認 | **×3**（Admin config high 等）＋Quantitys 庫存外洩 |
| 存取控制：跨帳號寫入／負數 | 已重現 | 原語就緒、agent 待精進（差自有 bid 推導） |
| JWT 敏感資料／錯誤訊息洩漏 | 無 | **×4**（hash in JWT＋錯誤頁 ×3，agent 自主） |
| 目錄列表／metrics／CSP／CORS／資訊 headers | 部分有 | **全部已確認** |
| 傳輸層／DNS 層／敏感檔 | 無 | **已確認** ×5 |
| 動態 UX／SEO/GEO | 無 | 7 項 |
| 證據可驗證性 | 工具報告 | rule_id→OWASP/CWE＋防偽編號＋SHA-256 查驗 |

**調研佐證**（`docs/research-dast-llm-pentest-2026.md`）：ZAP 2.17 full-scan
對同一靶機僅 5 類全組態級（0 注入、0 存取控制）——「整合經典工具」的天花板；
Argus 在組態、注入、存取控制三層都有自動化命中，且存取控制層是 LLM agent
自主完成（對手形態最接近 Burp/Autorize 的人驅動半自動）。

### 攻擊面打通的關鍵工程（2026-09-25 第二波）

#11→#16 的提升不是調參，是六個泛化能力（任何網站同樣生效）：

1. **爬蟲被動攔截 XHR/fetch 端點**（crawler.py）：SPA 的 API 呼叫只在真實
   瀏覽器流量裡；攔截後自動流入 Nuclei extra_urls 與 sqlmap 候選——
   `search?q=` 就是這樣進入攻擊面的（零新請求，純觀察）。
2. **Agent 網路感知工具 `get_network_requests`**（tools.py）：agent 能「看到」
   頁面發出的 API 請求，自行判斷哪些值得 probe——給眼睛不給答案。
   #16 實測 agent 第 1 步就呼叫它、第 3 步即對 `search?q=` 發動 probe。
3. **sqlmap `--level=3` ＋充足 timeout**：裸 `--batch`（level 1）對空值
   query 參數會在數秒內誤判不可注入；level 3 的完整驗證需 87~120+ 秒，
   120 秒 timeout 會邊緣超時（demo 提高到 240 秒消除時有時無）。
4. **Agent 反空轉與 token 壓縮**（loop.py）：歷史 DOM／文字快照每種只留
   最新一份（32 步 260k → 36 步 169k）；連續 ≥4 次同型動作注入策略導正。
5. **`probe_unauthorized_access`**：以無憑證的乾淨請求匿名重放同源端點，
   「是否屬於應受保護資料」由 agent 判斷——#16 命中 Admin 端點未授權
   存取（high）且零誤報（判斷 Quantitys 等公開資料不構成漏洞）。
6. **`report_security_issue` 觀察型回報**：帶證據的 agent 資安發現落地
   （severity 封頂 high——critical 保留給工具確認等級）＋ header 指紋
   規則補強（x-recruiting/x-generator/x-aspnet-version）。
7. **`replay_request` 登入態重放**：API 自註冊＋登入（token 寫入
   localStorage，JWT 於 snippet 中壓縮）＋帶憑證重放——IDOR（改 id）、
   business logic（改值）的通用原語；UI 表單泥沼（Angular mat-select
   讓 #17/#18 各耗 38/58 步）由 API 路徑取代（4 步閉環）。

### CVE 對應的設計（回答「能不能列 CVE」）

兩條既有路徑，指紋→CVE 全離線（NVD public domain / Retire.js 規則庫 vendored）：

| 路徑 | 輸入 | 比對庫 | 輸出 |
|---|---|---|---|
| `service_cve_scanner` | Server／X-Powered-By 版本指紋 | vendored NVD DB（`manage.py refresh_backend_cve_db` 更新） | per-CVE findings（severity 取最高、critical 封頂 high） |
| `js_library_scanner` | 頁面 `<script>` 的庫版本 | vendored Retire.js 規則庫 | per-CVE findings（A06/CWE-1104） |

Juice Shop 靶機上沒有可中的 CVE 屬**正確行為**：它不回 Server／X-Powered-By
（實渗無版本指紋可抽取），JS 庫版本無已知未修 CVE，靶機自身（v20.0.0）不在
NVD。真實網站帶版本指紋（nginx/PHP/Angular/jQuery 等）時即自動產出 CVE 清單。
加分方向（後續）：把 agent 發現的「版本資訊端點」（如 application-version）
接進 service_cve_scanner 的指紋輸入，擴大真實站的可中範圍。

### 對手「一個經典 GitHub 專案」的可行性比對（2026-09-25，GitHub API 直查）

對手宣稱：無 agent、用一個經典 GitHub 弱掃專案找到 12 項（含 IDOR ×2、
負數 business logic）。直查 GitHub（2026-09-25）：

| 查證 | 結果 |
|---|---|
| `IDOR detection scanner` 搜尋 | 最高 **46★**（Burp Suite extension——需 Burp 與人工操作）；其餘 ≤4★ |
| `automated pentesting business logic vulnerability` | **零結果** |
| Juice Shop 自動化解 | 僅 0★ 的寫死 E2E 腳本（Cypress/Playwright 逐 challenge 演練） |
| 學術實測（MilanRadic 2026） | ZAP 2.17 full-scan 對同靶機 **0 注入、0 邏輯類** |
| 能自動抓 IDOR/logic 的開源 | 僅 LLM 驅動框架：PentAGI（24.9k★）、CAI（9.8k★ archived）——**都是 agent** |
| skills 生態（skills.sh） | 無通用滲透技能（strix 系列＝商業 SaaS 自家技能，非可吸收知識） |

**推論**：「經典專案全自動找到 IDOR／負數」在 2026-09 的開源生態**不成立**。
對手實際形態最可能是：①手動滲透（Burp/瀏覽器）＋工具輔助、②寫死靶機的
腳本、③用了 LLM 框架而不自知其為 agent。共同點：**綁定特定靶機或人工
介入，不泛化**。Argus 黑箱＋雙 session 分工對未知網站同等適用——這是
說服力的來源。

### IDOR／business logic 的偵測方法論（2026-09-25 補）

本地原語驗證（curl 實測 Juice Shop）：B 帳號 token 讀他人 basket → **200
帶他人資料**（跨帳號讀取成立）；自己 basket POST `quantity=-5` → **200
且寫入**（負數成立）。兩者的共同前提＝「登入態＋請求修改重放」。

| 方法 | 誰能做到 | 自動化程度 |
|---|---|---|
| ZAP full-scan（傳統 DAST） | ✗（學術實測對 Juice Shop 0 邏輯類；官方 Access Control Testing 需手動錄雙 session 比對） | 手動設定 |
| Burp + Autorize 外掛（經典 GitHub 專案） | 半自動 IDOR（攔低權請求用他人 session 重放比對）；負數仍需手動 Repeater | 人驅動 |
| **Argus Hermes-Agent（replay_request）** | agent 自註冊登入 → 改 id 重放（IDOR）／改數值重放（logic）→ 帶證據回報 | **全自動** |

推論：對手「用一個經典 GitHub 專案就找到」的最可能形態＝Burp/Autorize
式的**人驅動半自動**；通用 DAST 不可能自動抓到這兩類。我們的形態是
LLM agent 自主完成同樣的原語操作，且方法對任何網站泛化（非靶機腳本）。

仍未涵蓋（誠實面）：**雙帳號視野比對**（A 建資料、B 盲改他人資料的
「寫入型 IDOR」需要兩個帳號的授權矩陣差分）——目前 agent 用單帳號的
「改 id 讀取」已覆蓋讀取型；寫入型屬後續功能（agent 開兩個 context）。

## 4. 模型升級（MiniMax-M2.7 → MiniMax-M3，2026-09-25 已落地）

調研結論（來源：MiniMax 官方部落格／platform.minimax.io／Artificial Analysis）：

- **MiniMax-M3**（2026-06-01 發佈）：428B MoE、1M context、與 M2.7 **同價**
  （$0.30/$1.20 per 1M tokens）、OpenAI Chat Completions 相容與 tool calling
  完整維持——升級零改動成本。
- 能力：SWE-bench Verified **80.5**（M2.7：56.2）、Terminal-Bench 2.1 66%
  （M2.7：57%）——agentic 能力大幅領前代。
- 已執行：`backend/apps/agent/providers.py` `default_model` 改為 `MiniMax-M3`，
  本地掃描實測 agent 迴圈 17 步無相容問題（token 用量與 M2.7 相當）。
- 注意：M3 為思考型模型，長迴圈的累積 token 較貼上限；本機 demo 疊加
  `ARGUS_AGENT_MAX_TOKENS=150000`，正式環境維持 60k 成本控制不變。
- 後續候選（若要再進一步，需新 API key，屬產品決策）：Qwen3.8 Max
  （τ-bench 雙榜第一）、Kimi K3（AA 44）、DeepSeek V4.1 Flash（成本半價）。

---

## 附錄：答辯問答彈藥

**Q：你們就是包 Nuclei/ZAP 吧？**
A：Nuclei/Katana 只是 Argus 資安維度的其中兩個工具（且被我們的授權閘門、
same-origin 限制、RPS 預算、取消機制包住）。自有引擎包含：Playwright BFS 爬蟲、
被動安全分析（headers/CSRF/PII/秘鑰）、深度掃描（SSL/TLS、Cookie、CORS/CSP 品質、
DNS SPF/DMARC/DNSSEC、SRI、JS 庫 CVE 離線比對、服務指紋 CVE）、敏感路徑探測、
AI agent 動態驗證。工具是被編排的資料來源之一，不是產品本身。

**Q：滲透測試你們做不了，怎麼跟 VAPT 比？**
A：Argus 的 Kali 鏈（sqlmap/metasploit，K8s Job 隔離執行＋Redis 原子預算＋
SHA-256 去重）已建置，正式環境基於攻擊面控制預設關閉（runbook 見
`docs/runbooks/kali-sqlmap-rollout.md`）——這是產品成熟度的表現：有攻擊能力，
但用授權閘門與隔離執行約束，而不是永遠開著。自動化「滲透」的正確形態是
AI-first：agent 判斷 → 工具驗證 → 證據落地，我們已實作這條路。

**Q：怎麼證明誤報率低？**
A：每筆 finding 帶 evidence 與檢測依據（rule_id → OWASP/CWE 對映），
Nuclei 探針被 WAF 擋時列為 info 不扣分（`scans/CLAUDE.md` 計分契約），
AI 確認的 security finding 與工具輸出分離落地。Juice Shop 對打時直接抽驗
findings 對照官方 challenge 清單即可量化。
