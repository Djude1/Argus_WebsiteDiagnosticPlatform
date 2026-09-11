# 票02：FixOutput 模型＋產生引擎（含事實政策驗證）

**日期**：2026-09-11  
**操作者**：Claude（ZCode）

## 變更內容
- `backend/apps/scans/models.py`：新增 `FixOutput`（與 ScanJob 一對一；狀態機 idle→generating→ready/failed；artifacts JSON 存四類產物＋逐欄位 fields 標註）。migration `0014_fixoutput`。
- `backend/apps/scans/fixgen/`（新套件）：
  - `facts.py`：從爬取頁面萃取事實（站名、電話、地址、email、社群連結、圖片候選、FAQ 問句、逐頁文字），構成驗證語料 corpus_norm。
  - `policy.py`：事實政策三級——識別類（語料比對，不符→佔位符【請填寫：…】）、文案類（硬事實 token 不在語料→退回逐字摘錄 extracted）、結構類免驗。
  - `engine.py`：prompt（只輸出欄位值的 JSON 契約）→ ProviderChain 單次 `chat_text` → 解析（容錯 markdown 圍欄）→ 逐欄位驗證 → 範本渲染（JSON-LD／OG＋meta／llms.txt／FAQPage）。
  - `services.py`：`start_fix_output`（條件式 update 原子搶占，冪等派工）＋`run_fix_output`（狀態收斂、失敗只留可公開原因）。
  - `tasks.py`：Celery 任務，不重試（花 token 的操作不得自動重複）。
- `backend/apps/agent/providers.py`（ additive）：`ChatProvider.chat_text`＋`ProviderChain.chat_text`——讓 MiniMax→GLM→**Gemini** 的文字 fallback 真正可用（原本 `chat_with_tools` 對純文字呼叫到不了 Gemini）；Gemini `chat_text` 補 temperature/maxOutputTokens。
- `backend/config/settings.py`：`ARGUS_FIXGEN_ENABLED`（預設 False）／`ARGUS_FIXGEN_MODEL`（空＝沿 provider 預設）／`ARGUS_FIXGEN_MAX_TOKENS`（4096）。
- 文件同步：`backend/CLAUDE.md` Model 速查＋FixOutput 條目、`backend/apps/scans/CLAUDE.md` 檔案職責表加 `fixgen/` 列。

## 原因
spec `docs/specs/0002-fix-output.md` 切票 02（`.scratch/fix-output/issues/02`）：LLM 只輸出欄位值、最終內容由範本確定性渲染，逐欄位事實驗證才有意義；站上無 FAQ 依據不產 FAQPage；每份 ScanJob 只產一次。

## 影響範圍
- 新功能獨立於掃描 pipeline（不影響既有掃描與計費）；啟用旗標預設關閉。
- `agent/providers.py` 的 chat_text 為純新增，Hermes tool-calling 行為不變。
- 計費尚未接線（票 03/04）：本票觸發產生不扣點。

## 驗證方式
- `uv run python backend/manage.py test apps.scans.tests_fixgen` → 10 tests OK（假 provider 注入：四產物 happy path、識別類佔位符、無 FAQ 不產、憑空問句丟棄、文案新增硬事實退回摘錄、未爬連結丟棄／sameAs partial、冪等單次派工、provider 失敗→failed、invalid JSON→failed、預設關閉→failed）。
- `uv run ruff check backend` 通過；`manage.py check` 無 issue。
- 完整套件 913 tests：僅 1 個既有環境錯誤（`tests_report_verification` Windows 檔案鎖定，票 01 時已驗證乾淨樹同樣失敗）。
