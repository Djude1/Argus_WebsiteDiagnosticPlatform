# 修正產出層：AEO/GEO 類直接產生可貼上修正內容，資安類維持交辦提示

既有 `Finding` 設計刻意停在「教使用者修」——`ai_handoff_prompt` 明確要求外部 LLM 不得輸出完整修復程式碼，`ai_explanation`／`ai_remediation` 欄位備而未用。競品（aeo.md5.com.tw）已示範「掃描後直接交付可複製貼上的修正碼」的真實需求；在「一站式健檢」定位（見 [`../../CONTEXT.md`](../../CONTEXT.md)）下，這是偵測→修正之間缺的最後一哩。

**決策**：推翻「不輸出完整修復程式碼」的既有立場，但**僅限 AEO/GEO 類**。v1 產物四類：JSON-LD（全站一份）、Open Graph＋meta 描述（首頁／代表頁，並補上現行 codebase 完全沒有的 OG 偵測）、llms.txt（以檔案下載交付，它是主機層檔案）、FAQPage Schema（僅當站上有可依據的 FAQ 內容才產生）。資安類維持文字 remediation＋交辦提示，v2 再評估低風險片段。

事實依據三級政策（信任生死線，也是與競品的差異化）：**識別類**欄位（機構名、地址、電話、社群連結）只准用爬到的事實，爬不到一律佔位符＋「請人工確認」；**結構類**（`og:type`、`@context`、locale）可由規則推導；**文案類**（meta description、FAQ 答案、llms.txt 摘要）只能改寫爬到的內文，禁止新增事實。每個產物附來源頁標註。

引擎與交付：重用 Hermes 的 ProviderChain（MiniMax→GLM→Gemini，正式 key 已就緒），另立 `ARGUS_FIXGEN_*` 環境變數（模型、token 上限可調）；bounded 單次結構化產生，非 agent 迴圈、不經 OpenCode。觸發：v1 為報告頁按鈕、按需觸發、Celery 非同步＋輪詢、失敗全額退點。計費：free/paid 二級自動判定（購點或完成付費掃描即 paid，不動金流），paid 掃描附贈 1 次產生額度（詞條見 CONTEXT.md），額度外固定點數（暫定 30 點，上線前以 rebuild 實際 token 成本校準）。資料模型：`FixOutput` 與 ScanJob 一對一，每份掃描產一次、重掃重新計費；前台報告頁新專區「修正產出」四分頁＋複製／下載（沿用既有 clipboard 模式）。v1 不含追問對話，v2 搬 rebuild 的 conversation／turn-trace 模式。

**為什麼**：AEO 片段自包含、貼錯頂多無效；資安設定片段貼錯（nginx/Apache/Cloudflare 語法各異）會把站弄掛——「敢不改字直接貼」是本功能的信任底線，寧可範圍窄。滲透測試 agent（clearwing／VulnClaw／PentestGPT）屬 CONTEXT.md 的「主動利用驗證」層工具，對第三方目標發動實際攻擊違反 ADR-0001 的被動邊界與 kali 休眠決策，且與內容產生任務不對口。

## 考慮過的選項

- **資安類也產可貼上片段**：貼錯風險不對稱；v2 限「被動、低破壞風險」類（安全 header、cookie 旗標）再評估。v1 否決。
- **掃描 pipeline 自動產生**：LLM 成本會被免費掃描灌爆；改按需觸發，等級制上線後對 paid 自動附贈即未來的「同步顯示」。v1 否決。
- **依實際 token 用量結算**：結算與 UI 複雜；採固定點數。否決。
- **v1 含多輪追問對話**：工程量大；rebuild 已有現成 conversation／turn-trace 模式可搬，晚做不吃虧。否決（v1）。
- **滲透 agent（clearwing／VulnClaw／PentestGPT）或 OpenClaw 作為產生引擎**：領域不對口；部署形態（本機 CLI、內建高風險工具、弱沙箱）不合多租戶 K8s。否決。**backlog spike**：評估 clearwing／PentestGPT 作為「主動利用驗證」層（kali 線）的引擎候選，受 kali 同款 disabled gate，不排期。
- **rebuild 同步遷移脫離 OpenCode**：動到既有已上線模組；列為獨立後續任務，不與本功能綁。本次否決。

## 後果

- `ai_handoff_prompt` 的「不輸出完整程式碼」語意改為僅適用資安類／未啟用修正產出的情境；`ai_remediation` 開始承接真內容（與 `FixOutput` 的分工在實作時於程式碼層定義）。
- billing 需新增「產生額度」概念與固定點數扣款 kind（`Kind` 枚舉擴充）；`FixOutput` 需新的狀態流（idle→generating→ready/failed）。
- Open Graph 偵測為全新 finding rule（現有 scanners／crawler／analyzers 零命中）。
- 文件同步：AGENTS.md／CLAUDE.md「CONTEXT.md 尚不存在」的過時描述隨本次一併修正。

詞彙定義見 [`../../CONTEXT.md`](../../CONTEXT.md)；被動邊界與 kali 線脈絡見 [`0001-backend-service-cve-fingerprinting-over-kali.md`](0001-backend-service-cve-fingerprinting-over-kali.md)。
