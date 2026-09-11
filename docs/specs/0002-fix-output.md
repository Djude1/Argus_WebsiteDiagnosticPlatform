# Spec: 修正產出（Fix Output）——AEO/GEO 可貼上修正內容

> 本檔為 PRD（spec 原始來源）。方向決策見 [`../adr/0002-fix-output-over-handoff-prompt.md`](../adr/0002-fix-output-over-handoff-prompt.md)；詞彙定義見 [`../../CONTEXT.md`](../../CONTEXT.md)（修正產出、產生額度、AEO、GEO、一站式健檢）。

## Problem Statement

網站管理者用 Argus 做完一站式健檢後，AEO/GEO 維度的報告只告訴他「缺 JSON-LD」「缺 meta description」「沒有 llms.txt」——偵測到了問題，但修正要自己來：管理者得查 schema.org 文件、手寫 structured data、湊 Open Graph 標籤、從無到有草擬 llms.txt。這對不熟 SEO/AEO 的管理者門檻極高，報告的行動價值斷在「知道問題」與「能修問題」之間。競品（AEO Spider 類工具）已示範「掃描後直接交付可複製貼上的修正碼」是真實需求。Argus 的 `Finding` 上雖備有 AI 欄位，但既有設計刻意只產「交辦提示」、不輸出完整程式碼——這條線在 AEO/GEO 類上應該跨過去（ADR-0002）。

## Solution

掃描完成後，管理者在報告頁的「**修正產出**」專區按「產生修正內容」，Argus 以掃描爬到的網站內容為事實基礎，自動產生四類可直接採用的修正產出：JSON-LD（全站一份）、Open Graph＋meta 描述（首頁／代表頁）、llms.txt（檔案下載）、FAQPage Schema（僅當站上有可依據的 FAQ 內容）。每個產物逐欄位標註事實來源；爬不到的識別類欄位（地址、電話、社群連結等）以明顯佔位符呈現並標「請人工確認」，**絕不編造**。付費掃描附贈 1 次產生額度，額度外按固定點數計費，產生失敗全額退點。資安類 finding 維持文字修補建議＋交辦提示，不提供可貼上設定檔。

## User Stories

1. 作為網站管理者，我希望掃描報告直接給我可貼上的 JSON-LD 區塊，這樣我不必查 schema.org 文件手寫 structured data。
2. 作為網站管理者，我希望拿到完整的 Open Graph＋Twitter Card＋meta 描述標籤組，這樣社群分享與搜尋結果呈現立即改善。
3. 作為網站管理者，我希望直接下載現成的 llms.txt 檔案，這樣我只需上傳到主機根目錄。
4. 作為網站管理者，我希望只在站上真的有 FAQ 內容時才收到 FAQPage Schema，這樣我不會拿到憑空編造的問答。
5. 作為網站管理者，我希望產出內容只引用我網站上真的存在的資訊，這樣我敢不改字直接複製貼上。
6. 作為網站管理者，我希望爬不到的欄位（如分機號碼、官方社群帳號）以明顯佔位符標示「請人工確認」，這樣我不會誤把猜測值當事實貼上線。
7. 作為網站管理者，我希望每個產物附來源頁標註（哪個欄位來自哪一頁），這樣我可以查證並快速人工覆核。
8. 作為網站管理者，我希望修正產出以獨立專區＋分頁呈現（JSON-LD／OG＋meta／llms.txt／FAQ Schema），這樣我能對照報告 finding 逐項採用。
9. 作為網站管理者，我希望每個程式碼區塊有一鍵複製按鈕，這樣貼進我的 CMS 或 HTML 不用手動選取。
10. 作為網站管理者，我希望掃描報告也能偵測 Open Graph 標籤缺失，這樣我知道社群分享目前的呈現缺口。
11. 作為付費使用者，我希望每次付費掃描自動附贈 1 次修正產出額度，這樣付費有明確加值感。
12. 作為付費使用者，我希望額度用完後能以固定點數（暫定 30 點）按次加購，這樣費用可預期。
13. 作為使用者，我希望產生過程非同步顯示進度（產生中→完成），這樣我知道系統在跑、不用乾等。
14. 作為使用者，我希望產生失敗（LLM 逾時等）時全額退點，這樣我不為失敗的產出付費。
15. 作為使用者，我希望同一次掃描的產出可無限次重看、重複複製，這樣不會重複計費。
16. 作為使用者，我希望重新掃描後才需要重新產生（重新計費），這樣額度對應的是「一份掃描結果」。
17. 作為免費使用者，我希望 quick-scan 結果頁告訴我「完整掃描可獲得可直接貼上的修正內容」，這樣我知道升級付費能換到什麼。
18. 作為安全意識高的管理者，我希望資安類 finding 不提供可直接貼上的伺服器設定片段，這樣我不會因貼錯 nginx/Apache 語法把站弄掛。
19. 作為平台維運者，我希望產生引擎的模型與 token 上限用環境變數控制（`ARGUS_FIXGEN_*`），這樣換模型或調成本不用改程式碼。
20. 作為平台維運者，我希望產出走既有 LLM provider 鏈（MiniMax→GLM→Gemini），這樣正式環境金鑰與 fallback 機制直接沿用。
21. 作為平台維運者，我希望產生失敗會留下明確的 failed 狀態與原因，這樣不會出現卡在「產生中」的殭屍紀錄。
22. 作為平台維運者，我希望額度贈與、點數扣款、退款都走 billing 既有 services 函式並留交易紀錄，這樣計費可稽核。
23. 作為開發維護者，我希望產出以與 ScanJob 一對一的模型儲存（狀態機 idle→generating→ready/failed），這樣重看不重算、狀態可查。
24. 作為開發維護者，我希望事實政策（識別／結構／文案三級）在產生後有獨立驗證步驟，這樣 LLM 越界輸出會被攔截取代。
25. 作為開發維護者，我希望產生流程以假 provider 可測（不依賴真實 LLM），這樣測試穩定不 flaky。
26. 作為網站管理者，我希望產出專區只在掃描完成後出現在報告頁，這樣不會對進行中的掃描誤觸。

## Implementation Decisions

- **資料模型**：`FixOutput` 與 `ScanJob` 一對一。JSON 欄位存四類產物（各含內容本體＋逐欄位來源標註）；狀態機 `idle → generating → ready / failed`，failed 記錄原因。每份 ScanJob 只產一次（幂等：重複觸發回傳既有結果，不重複計費）。
- **新偵測规则**：Open Graph 偵測為全新 finding rule（og:title/og:description/og:image/og:url 缺失），併入既有 SEO/GEO 掃描維度與計分；此為現有 scanner 零覆蓋的空白。
- **產生引擎**：重用 Hermes 的 ProviderChain（MiniMax→GLM→Gemini fallback），另立 `ARGUS_FIXGEN_*` 環境變數（啟用旗標、模型、token 上限）。bounded 單次結構化產生（JSON output），非 agent 迴圈、不經 OpenCode、不經 Hermes 的 Playwright 流程。
- **事實政策三級**（產生後驗證步驟強制執行）：
  - 識別類（機構名、地址、電話、社群連結）：只能用爬到的事實；驗證步驟比對爬取內容，不符即取代為佔位符（統一樣式 `【請填寫：…】`）。
  - 結構類（`og:type`、`@context`、locale、URL 組型）：可由規則推導。
  - 文案類（meta description、FAQ 答案、llms.txt 摘要）：只能改寫爬到的內文，驗證步驟攔截新增事實。
- **觸發與交付**：報告頁「修正產出」專區的「產生修正內容」按鈕 → API endpoint → Celery 非同步任務 → 前端輪詢狀態。產出分兩種交付型態：HTML 片段（JSON-LD／OG／FAQ，複製貼上）與主機檔案（llms.txt，下載）。
- **計費**：free/paid 二級自動判定（曾購點數包或完成付費掃描即 paid），不動綠界金流。付費掃描結算時贈與 1 次產生額度；額度外每次固定 30 點（上線前以 rebuild 實際 token 成本校準）。所有寫入走 billing services 既有函式模式；`CoinTransaction.Kind` 擴充對應枚舉（贈與／扣款／退款）。失敗全額退點。
- **範圍邊界**：產出範圍＝全站一份（組織級 JSON-LD、llms.txt）＋首頁／代表頁（OG＋meta、FAQ Schema）；不逐頁全套。資安類 finding 不產可貼上內容（v2 再評估低風險 header 類）。
- **v1 明確不含**：產出後的多輪追問對話（v2 搬 rebuild 的 conversation／turn-trace 模式）、掃描 pipeline 自動產生（等級制上線後對 paid 自動附贈即是未來「同步顯示」形態）。
- **quick-scan**：僅在結果頁加 CTA 文案導流，不做免費產生。

## Testing Decisions

好測試只驗**模組公開函式的對外行為**，不驗內部實作；LLM 相關測試一律注入假 provider，與真實 API 脫鉤（apps/agent 既有 provider patch 模式、apps/rebuild 既有「LLM 產生＋計費結算」測試模式）。

- **Seam 1（唯一新接縫）— 產生服務邊界**：種入含已知內容的 ScanJob＋Page（地址、電話、FAQ 段落等），把 ProviderChain 換成假 provider 餵固定輸出，斷言：
  - 四類產物正確產出、狀態機推進（idle→generating→ready；LLM 失敗→failed）。
  - 事實政策真的擋得住：假 LLM 輸出含爬不到的識別類事實 → 被佔位符取代；來源標註對應正確。
  - 站上無 FAQ 依據 → 不產 FAQPage Schema。
  - 幂等：同 ScanJob 重複觸發不重複計費、不覆蓋既有結果。
- **既有接縫擴充（不新增）**：
  - billing services 測試擴充：額度贈與、固定點數扣款、失敗退款、交易紀錄種類（prior art：billing 既有 tests）。
  - API 測試以 Django test client 驗觸發／狀態／產物讀取端點（prior art：scans 既有 API 測試）。
  - OG 偵測以合成頁面驗 finding 產出（prior art：scanner 類 tests_*.py 慣例）。
- **測試檔命名**：跟隨 scans app `tests_<主題>.py` 慣例。
- **前端**：repo 無 JS 測試基礎建設，不納入自動測試；以手動驗證清單處理（複製按鈕、下載、輪詢狀態顯示）。
- 全後端測試套件必須全數通過。

## Out of Scope

- 資安類 finding 的可貼上修正片段（v2 評估「被動、低破壞風險」類）。
- 產出後多輪追問對話與思考軌跡 UI（v2 搬 rebuild conversation／turn-trace 模式）。
- 掃描 pipeline 內自動產生／掃描完成同步顯示（待等級制上線後）。
- 訂閱制金流、綠界變更。
- rebuild 模組遷移脫離 OpenCode（獨立後續任務）。
- 滲透 agent（clearwing／VulnClaw／PentestGPT）整合（backlog spike 另案，見 ADR-0002）。
- sitemap.xml 偵測、逐頁全套產出。

## Further Notes

- 詞彙以 [`CONTEXT.md`](../../CONTEXT.md) 為準：修正產出（Fix Output）、產生額度（Generation Entitlement）、AEO、GEO、一站式健檢。
- 建議實作切票順序（每票獨立 commit，符合使用者「小功能即 commit」習慣）：
  1. Open Graph 偵測 finding rule
  2. `FixOutput` 模型＋migration＋狀態機
  3. `ARGUS_FIXGEN_*` 設定＋產生 Celery task（ProviderChain 重用＋事實政策驗證）
  4. billing 產生額度與 Kind 擴充（贈與／扣款／退款）
  5. 觸發／狀態／產物 API endpoint
  6. 報告頁「修正產出」專區（四分頁＋複製／下載＋輪詢）
  7. quick-scan CTA 文案
- 30 點定價為暫定值，上線前以 rebuild 實際 token 成本校準。
- 前端 build 一律走 `frontend/build-node22.ps1`；環境驗證依 `docs/environment-preflight.md`。
