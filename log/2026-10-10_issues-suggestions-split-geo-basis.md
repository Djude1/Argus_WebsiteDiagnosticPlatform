# 問題分析頁軟建議分區 ＋ GEO 內容規則研究依據

**日期**：2026-10-10  
**操作者**：Claude

## 變更內容
會員掃描相關頁面優化升級的其中兩項（使用者指定「做 1 和 3」）：

### 1. 問題分析頁：info 軟建議獨立成「可強化的建議」區塊（前端）
`frontend/src/features/projects/ProjectPages.jsx` 的 `ProjectIssuesPage`：

- 列表模式（`group=all`）把 `info` 嚴重度的問題（多為 GEO 內容訊號、加分項，計分上本來就不扣分）從主問題表拆出，另放一個「可強化的建議（N）」區塊（同一張 `issue-table`、可展開看詳情與證據，沿用 `IssueRow`）。
- 主問題表只留需處理的項目（critical／high／medium／low）。
- 依嚴重度分組／依根本原因兩種模式維持原本完整分組，不拆（那兩個模式本來就是刻意按該維度呈現）。
- 邊界：嚴重度篩成 `info` 時主問題表顯示「沒有需要處理的問題，只有下方的建議項目」，建議仍列在下方區塊；完全沒有符合條件時維持原空狀態文案。
- CSV 匯出、摘要計數、嚴重度徽章不變（info 仍計入問題總數）。

### 3. GEO 內容訊號規則：報告逐項附研究依據（後端）
`backend/apps/scans/reports.py` 的 `RULE_BASIS` 新增 5 筆（原本這些 GEO 軟規則只套用維度通用的 `CATEGORY_BASIS["geo"]`）：

- `geo-citability-no-sources`／`-no-statistics`／`-no-quotations`：依據 Princeton「GEO: Generative Engine Optimization」(Aggarwal et al., KDD 2024) GEO-bench 實測（補來源 +27%、統計數字 +33%、專家引言 +41%），並附限制（研究平均相關性、非個別網站保證、軟訊號）。
- `geo-content-decay`：依據（時效內容缺更新日期訊號不利 AI 確認正確性）與限制（只看文字樣式、不判斷實際過時）。
- `geo-rag-chunking`：依據（生成式引擎以區段檢索，過長不利乾淨擷取；SE Ranking 2026 觀察約 100–150 字區段被引用率較高）與限制（以小標題數估算、非精確切塊）。

報告 `_report_finding_entry` 既有邏輯（非資安 finding 一律取 `RULE_BASIS.get()` → `AXE_BASIS` → `CATEGORY_BASIS`）自動讓這些 finding 改用專屬依據，無需改呈現層。

## 原因
使用者先前要求「對會員掃描頁面和各問題頁面繼續優化升級」，在候選項目中指定做 1（問題分析可讀性：把軟建議與真問題分開，避免 GEO 內容軟訊號稀釋待辦重點）與 3（讓新加的 GEO 內容規則在報告上交代研究出處與限制，誠實且有說服力）。

## 影響範圍
- 前端：問題分析頁列表模式版面調整；無新 API、無資料結構變更；不影響分組模式與其他分頁。
- 後端：報告逐項「判定依據」文字；不改嚴重度、不改計分、不改 finding 產生邏輯。`RENDERER_VERSION` 不變（只是既有 basis 欄位換更精準的字串，非版面結構變更）。
- 皆為既有功能的呈現優化（可讀性／說明文字），非新對外功能、API、model 或計費流程異動，未動競賽需求書 Word md。

## 驗證方式
- 後端：`manage.py test apps.scans.tests_geo_citability apps.scans.tests_geo_decay apps.scans.tests_geo_rag apps.scans.tests_report_payload apps.scans.tests_layout_shift`（38 項通過，3 略過）；新增各規則 `test_rule(s)_have_report_basis` 鎖定 RULE_BASIS 有登記。`ruff check` 通過。
- 前端：`npm run lint`（0 error，1 項既有無關 warning）、`npm run typecheck` 通過、`npx vitest run src/features/projects`（30 項通過）。

## 文件同步
- `frontend/CLAUDE.md`：`/projects/:id/issues` 路由說明補列表模式軟建議分區。
- `backend/apps/scans/CLAUDE.md`：`geo_citability.py` 行補報告依據附研究出處。
