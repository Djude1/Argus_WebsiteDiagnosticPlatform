# 三份規劃文件（ADR-0004、掃描 Roadmap、商業模式計劃書）審查修訂

**日期**：2026-10-07
**操作者**：Claude

## 變更內容
以 ChatGPT 修訂後的 `origin/main` 版本為基礎（先 fast-forward 合併到工作分支），逐條對照程式碼後修正 16 處：

- `docs/adr/0004-smart-dynamic-scan.md`
  - 「Advanced Dynamic Scan」改正為 Tenable Nessus 的掃描範本（原誤植為 Acunetix），並說明 Nessus 是使用者自訂外掛篩選、Argus 是依指紋自動選模組。
  - 原則 2 改正：現行掃描計費已是上限預扣＋依實際頁數結算（`settle_scan_actual`），智慧掃描只是把結算依據延伸到實際執行的模組。
  - 開頭改正：目前是被動／主動兩種模式；刪除「純靜態站跑 Auth/API 空轉」（系統沒有這類模組）。
  - 資料模型明定新增 `scan_strategy` 欄位，禁止把 smart 塞進 `scan_mode`。
  - 階段 3 改為「掃描策略」選項，不做成三選一；階段 2 補 `scan_strategy` migration。
  - ZAP 補部署與資源：獨立 namespace 的 K8s Job、資源上限、NetworkPolicy、映像檔 digest、功能旗標、上線前實測成本。
- `docs/scan-upgrade-roadmap.md`
  - AEO：`entails()` 答案蘊含與日期衝突判定已存在（第二輪），P0 改為量測與強化；衝突判定擴到價格與聯絡方式。
  - P0-B 驗收：Email 矛盾案例第二輪已修正，改為納入回歸測試＋改由同一份 evidence 產生。
  - 敏感檔案探測從「被動資安」移到「主動探測」（`run_exposure` 只在主動＋已授權＋整站開啟）。
  - llms.txt 標為部分完成；掃描設定檔化對齊 `scan_strategy`。
- `docs/business-model-plan.md`
  - 修正 §3.3 表格 C 列（殘留舊文字造成欄數錯亂且前後矛盾）。
  - 新增「Standard Full Scan」名詞定義（被動、整站、五面向、最多 50 頁、含 UX 測試，預扣 520 點）。
  - 濫用評估分 A／B 方案，補 B 方案（首次免費完整掃描）的分析。
  - 名詞「新手禮」統一為「首次免費完整掃描」（A 方案名稱除外）。
  - §6.5 補回「深度資安 Agent 目前不收費、派工沒有上限」。
  - 程式改動範圍改為額度紀錄（需 migration）與 Partial Scan 確認流程。

## 原因
使用者請 ChatGPT 修訂三份文件後，要我再確認；審查發現事實錯誤、文件內部矛盾與缺漏共 16 處，使用者要求全部直接修改。

## 影響範圍
- 只修改文件，未改動任何程式或設定。
- 三份都是尚未實作的規劃文件，對外可見功能未異動，競賽 Word 內容 md 本次不需同步。

## 驗證方式
- 事實逐條對照程式：`scan_plan.py`（`run_exposure` 條件）、`billing/services.py`（`settle_scan_actual`）、`aeo/answers.py`（`entails()`、衝突只判日期）、`aeo/content.py`（`_is_body_text`）、`seo/collect.py` 與 `link_check.py`（去重與並發）、`crawler.py`（`domcontentloaded`）、`models.py`（`Finding.confidence` 預設 1.0）。
- Nessus「Advanced Dynamic Scan」以 Tenable 官方文件確認。
- 依 `docs/md-checklist.md`：三份文件所有 Markdown 表格欄數一致；文件內引用的 repo 路徑全部存在；跨文件對 `scan_strategy`／`scan_mode` 的說法一致。
