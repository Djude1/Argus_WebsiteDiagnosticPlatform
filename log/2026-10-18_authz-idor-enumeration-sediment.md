# 確定性沉澱：未授權 IDOR／BOLA 枚舉＋父集合反推

**日期**：2026-10-18
**操作者**：Claude
**來源**：juice-shop 前後兩次報告對比（EB44 vs 8AC2）發現——8AC2 那次 AI Agent 幾乎沒跑起來
（14→1 筆），一大串 IDOR／成批外洩只剩 agent 偶發才抓得到。使用者要求「先把確定性沉澱做了，
agent 另外查」。

## 問題
`authz_probe` 的成批名單檢查（`security-unauth-api-records`）判定夠扎實，但有兩個缺口讓 juice-shop
那類未授權漏洞漏掉：
1. **探測端點只來自爬到／JS 抽到的**（`_observed_api_paths`）。淺爬 SPA 時那些 list 端點沒被觀察到
   → 根本沒探。
2. **完全沒有 IDOR／BOLA 枚舉**（改 `/:id` 看別人物件）——這個類別只有 agent 會做。

## 修法（通用、不寫死目標路徑，黑箱泛化鐵律）
`security/authz_probe.py`：
- `_id_template(path)`：路徑結尾純數字 → `(模板, id)`（`/x/29` → `/x/#`）。只認純數字（避免把
  slug／uuid 當 id 枚舉，控請求量與誤報）。
- `expand_idor_candidates(urls)`：對觀察到的 `/集合/:id` 反推兩種額外探測目標——**父集合**（去 id，
  成批外洩其實在這）與**鄰近 id**（1／2／3＋觀察值）。每模板只展一次、最多 `MAX_IDOR_TEMPLATES`＝5。
- `analyze_idor_results(results)`：單筆物件型 IDOR——同一模板 ≥2 個不同 id 未授權都回 200、內容
  **互異**的單筆物件（排除所有 id 回同一頁的 SPA／靜態）、且帶身分／內部／個資欄位
  → `security-idor-enumerable-object`（A01／CWE-639）。頂層陣列交回成批檢查不重複。
- 判定門檻抽成 `_sensitivity(keys_blob, pii)`，成批名單與 IDOR **共用**（身分＋內部／敏感欄位名／
  強個資任一；email／手機弱個資不單獨成立）。重構 `analyze_unauthorized_results` 改用它，行為不變。

`tasks._run_authz_probe`：候選 = 觀察端點 ＋ `expand_idor_candidates(...)`，統一去重套 `MAX_ENDPOINTS`；
findings = `analyze_unauthorized_results` ＋ `analyze_idor_results`。

## 範圍誠實說明
只打得到**未授權**就能枚舉的 IDOR（改 id 不需登入）。juice-shop 多數 IDOR（/api/Users、/rest/basket、
/api/Cards…）是**登入後**才開放，確定性層沒帳密打不到，仍要靠 agent 或帶帳密掃描——這刀不涵蓋那些，
不過度承諾。能沉澱的是「未授權成批外洩（父集合反推補上覆蓋）」與「未授權逐物件 IDOR」。

## 驗證
- `tests_authz_probe`（24，+12）：`ExpandIdorCandidatesTests`（父集合＋鄰近 id、非數字結尾不展、
  同模板只展一次）、`AnalyzeIdorResultsTests`（可枚舉物件、PII 升 high、包一層單筆、公開 /產品/:id 不報、
  所有 id 同頁不報、單一 id 不報、頂層陣列交回成批、非 200 略過）。
- `tests_authz_probe ＋ tests_pipeline_stages ＋ tests_coverage`（63）通過；`ruff check backend` 乾淨。
- 文件同步 `security/CLAUDE.md` authz_probe 條目。

## 待辦
- agent 8AC2 為何只跑 1 筆：等正式環境 `warning_summary["agent"]`（status/steps/tokens/error/feedback）
  貼回判定「預算 vs 2026-10-18 coverage_summary prompt 回歸」。
- 需登入的 IDOR／寫入型 IDOR／業務邏輯（負值數量）仍是 agent／帶帳密掃描範圍。
- 待 rebuild backend image 後本刀生效。
