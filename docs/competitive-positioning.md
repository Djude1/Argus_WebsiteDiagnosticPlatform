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

### 本地實測紀錄（2026-09-25，掃描 #9→#16 迭代）

同一靶機（`http://juice-shop:3000`，active＋authorized、全網站、max_pages=15），
Docker 完整堆疊＝K8s 正式功能面（Agent 開啟）＋demo 攻擊鏈（Kali docker backend）。

| 指標 | #11（首輪完成） | #13（攻擊面打通） | #14（反空轉） | **#16（最終）** |
|---|---|---|---|---|
| findings（DB／報告合併後） | 16／16 | 15／14 | 18／17 | **22／18**（2C+3H+9M+5L+3I） |
| 應用層攻擊命中 | 0 | SQLi critical | ＋目錄列表×2＋metrics | **＋未授權存取×3＋x-recruiting** |
| Hermes-Agent | 20 步 3 UX | 32 步爆 token | 36 步完成 1 issue | **25 步 66k：probe 序列＋帶證據回報×3** |
| 總分 | 65 | 61 | 70 | 72 |

**#16 偵測清單 vs 對手 12 項**（同靶機直接對打）：

| 類別 | 對手（經典工具整合） | Argus #16 |
|---|---|---|
| SQL injection | 已重現 ×2（登入＋搜尋） | **sqlmap 工具確認 ×2**（boolean/stacked/time-based/union 四技法、SQLite，證據鏈完整） |
| 存取控制（未授權存取） | 已重現 ×3（跨帳號/負數） | **agent-observed ×3**：Admin application-configuration 未授權（high）、application-version（medium）、500 錯誤頁洩漏路由堆疊（low）——agent 匿名重放＋帶證據判斷，零誤報 |
| 目錄列表 `/ftp/` | 已確認 | **已確認**（×2，Apache 與 Express 格式都支援） |
| 監控 `/metrics` | 未確認 | **已確認** |
| CSP／CORS | 已確認／待驗證 | **已確認** |
| 資訊類 headers（x-recruiting 等） | 資訊性 | **已確認**（x-recruiting＋x-powered-by 類指紋規則） |
| 傳輸層（HTTPS/HSTS）／DNS 層（SPF/DMARC）／敏感檔 | 無 | **已確認** ×5 |
| 動態 UX／SEO/GEO/AEO | 無 | 7 項 |
| 證據可驗證性 | 工具報告 | 每項帶 rule_id→OWASP/CWE＋報告防偽編號＋SHA-256 查驗 |

**調研佐證**（`docs/research-dast-llm-pentest-2026.md`）：ZAP 2.17 full-scan
對同一靶機僅 5 類全組態級（0 注入、0 存取控制）——「整合經典工具」的天花板；
Argus #16 在組態層數量超越、注入層有工具確認 critical、存取控制層有 agent
帶證據的未授權存取發現。

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

仍未涵蓋（誠實面）：跨帳號讀寫（IDOR）與負數數量需要兩個登入帳號的
比對測試，屬後續功能（agent 帶認證 context 的多角色流程）。

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
