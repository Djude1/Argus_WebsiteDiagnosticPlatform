# 修正產出功能規劃定案（grill-with-docs）

**日期**：2026-09-09
**操作者**：Claude（ZCode，grill-with-docs 訪談）

## 變更內容

- 純規劃 session，**無程式碼變更**
- `CONTEXT.md`：新增「一站式健檢」「AEO」「GEO」「修正產出」「產生額度」五個詞條（含與 ADR-0001 主軸敘事的關係釐清）
- `docs/adr/0002-fix-output-over-handoff-prompt.md`：新增 ADR——推翻「僅交辦提示、不輸出完整程式碼」立場（限 AEO/GEO 類）、v1 四類產物、事實依據三級政策、引擎（重用 Hermes ProviderChain＋`ARGUS_FIXGEN_*`）、free/paid 二級計費與產生額度、backlog spike（clearwing／PentestGPT）
- `AGENTS.md`／`CLAUDE.md`：「`CONTEXT.md`／`docs/adr/` 目前皆尚未存在」的過時描述已改為「已存在，持續維護」（改動存在工作區；因兩檔混有其他任務的未提交變更，未隨本 log 的 commit 提交，留待一併處理）

## 原因

使用者參考 aeo.md5.com.tw（掃描後直接列出需修改內容並給可複製貼上的修正碼），提出「是否新增等級或功能，讓 agent 自動撰寫所有要修改的內容」。經三輪 grill-with-docs 訪談定案：v1 做「修正產出層」（AEO/GEO 四類產物），資安類不產 code；觸發、快取、計費、引擎、範圍逐項定案如 ADR-0002。

## 影響範圍

- 後續開發任務（未開始）：`FixOutput` 模型（與 ScanJob 一對一）、Open Graph 偵測 finding rule、修正產生 Celery task、報告頁「修正產出」專區（四分頁＋複製/下載）、billing 額度概念與 `Kind` 枚舉擴充、`ARGUS_FIXGEN_*` 設定
- rebuild 模組不動：OpenCode 維持現狀，遷移到自研引擎列為獨立後續任務
- backlog spike：clearwing／PentestGPT 作為「主動利用驗證」層（kali 線）引擎候選，受同款 disabled gate，不排期
- Hermes-Agent 本身不受影響（只重用其 ProviderChain 基建）

## 驗證方式

- `docs/md-checklist.md` A–D 逐項核對（跨檔一致、引用路徑存在、無矛盾、同步完整）
- `rg -n "尚未存在" AGENTS.md CLAUDE.md` 確認無殘留過時描述
- `ls docs/adr/` 確認 0001／0002 並存、編號連續
- 純文件變更，無程式碼測試項目
