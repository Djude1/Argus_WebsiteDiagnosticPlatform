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

### 本地實測紀錄（2026-09-25，掃描 #9/#10/#11）

三輪掃描同一靶機（`http://juice-shop:3000`，active＋authorized、全網站模式、
max_pages=15），功能面＝K8s 正式環境（Redis/Celery/PostgreSQL/Playwright/
Nuclei v3.8.0/Katana v1.1.2/Hermes-Agent 開啟）＋疊加 demo 攻擊鏈（Kali docker
backend、sqlmap 1.10.6）。

| 指標 | #9（首輪） | #10（修 Nuclei 私網封鎖） | #11（最終：900s＋Kali＋M3） |
|---|---|---|---|
| 完整掃描耗時 | 約 2.3 分 | 約 7.2 分 | 約 18 分 |
| findings 總數 | 13 | 13 | **16**（2 高/7 中/5 低/2 資訊） |
| security 分數 | 9/100 | 9/100 | 9/100（靶機滿漏洞，低分＝偵測正確） |
| Hermes-Agent | 爆 token 上限中止（63,086>60,000） | 17 步完成、0 issues | **20 步完成、3 個 UX findings** |
| Kali sqlmap | disabled（K8s 基線） | disabled | **執行 3 target**（首頁無 query 參數，confirmed=False） |
| 授權閘門 | VerifiedDomain admin override 走正式 API 流程（AdminAuditLog 留痕） | 同左 | 同左 |

Agent 發現的 3 項（僅 #11，模型升級 M2.7→M3 後出現；同 token 量下 M2.7 兩輪皆 0）：

1. 搜尋按鈕無法被點擊（互動無回應）— medium
2. Cookie 同意橫幅文案語意不清 — medium
3. 「dismiss cookie message」按鈕無法被點擊 — low

報告：16 頁 Word（329 KB），視覺驗收 16/16 通過（圖表 CJK 正常、嚴重度色塊
一致、發現數自洽）；防偽編號＋內容 SHA-256 指紋＋公開查驗端點 `matches=True`
實測通過。樣本存於 `log_assets_juice/`。

**已知覆蓋限制（誠實面對）**：Juice Shop 是 Angular SPA，BFS 爬蟲僅得 2 個唯一
URL——深層 API 端點（`/rest/products/search?q=` 等）不在種子內，故 Nuclei
與 sqlmap 的有效輸入面受限。Nuclei 全模板在 2 RPS 預算下需 50+ 分鐘，900 秒
上限內必然截斷（產品對目標站的保護取捨）。改善方向（後續功能）：使用者在建立
掃描時可附 seed URL 清單，直接餵給 Nuclei/Katana/sqlmap 候選。

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
