# 系統名稱改為「Argus AI網站健檢平台」

**日期**：2026-10-10  
**操作者**：Claude

## 變更內容
使用者要求把 `69b7f7c`（2026-10-09 系統名稱統一為「Argus 網站健檢平台」）改動到的名稱，一律改成「Argus AI網站健檢平台」（依使用者寫法，「AI」與「網站」之間不空格）。只動該 commit 改過的檔案：

- 前台：`index.html`（title、description、og／twitter）、`manifest.webmanifest`（name、description）、導覽列小字與 logo alt（`SiteNav.jsx`）、`ArgusLogo` 預設副標、登入頁兩處副標（`AuthPages.jsx`）、公開頁頁尾副標與版權列（`PublicPages.jsx`）、`64-project-switcher.css` 註解。
- 後端：帳號信與收據信署名（`accounts/emails.py`、`billing/emails.py`）、MCP 伺服器說明（`mcp_access/protocol.py`）、PDF 報告頁尾（`report_render/report.py`，`RENDERER_VERSION` 21 → 22，舊報告下載時重新產生）。
- 文件：`README.md`（標題、目錄錨點、簡介）、`ONBOARDING.md`、`pyproject.toml` description、`.claude/agents/security-reviewer.md`、`.codex/agents/security-reviewer.toml`、`backend/apps/scans/CLAUDE.md`（RENDERER_VERSION 說明）。
- 競賽文件：`需求書_複賽版完整內容.md` 封面（AI網站健檢平台／AI Website Health Check Platform）與系統名稱表格；`需求書_複賽版_修訂提示詞包.md` 新增 R10（R9 可能已套用到 Word，不改寫 R9，以 R10 接續並取代 R9 中「Argus 網站健檢平台」的驗收項）。
- 保留不動：`log/2026-10-09_project-name.md`（歷史紀錄）、RENDERER_VERSION 註解裡「20：頁尾品牌改為『Argus 網站健檢平台』」的版本沿革。

## 原因
使用者決定系統名稱加回「AI」。

## 影響範圍
- 使用者看得到的名稱：分頁標題、PWA 安裝名稱、導覽列／登入頁／頁尾、系統信、PDF 頁尾、MCP 說明。
- 不在 `69b7f7c` 範圍、使用者確認後一併改名（fix-a）：`SharedOptimizationPage.jsx` 的品牌 aria-label、`LegalPages.jsx` 隱私權政策與服務條款開頭（只改名稱，資料處理方式未變，`EFFECTIVE_DATE` 不動）、`docs/opencode-agents/argus-rebuild.md` agent 提示詞。歷史規劃文件與 log 不改。

## 驗證方式
- `ruff check backend` 通過；`manage.py test apps.accounts apps.billing apps.mcp_access apps.scans.tests_report_layout apps.scans.tests_report_payload`（241 項通過）。
- 前端 `npm run lint`（0 error）、`npm run typecheck`、`npx vitest run`（43 檔 272 項通過）；`manifest.webmanifest` JSON 解析正常。
- Word 檔需依 R10 套用後以關鍵字驗收。
