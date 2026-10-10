# UX 假按鈕檢查（借鑑 claude-seo）

**日期**：2026-10-10  
**操作者**：Claude

## 變更內容
借鑑 claude-seo（MIT, AgriciDaniel）的 agent_ux_check「真按鈕 vs `<div onclick>`」判定，做成 Argus 的 UX 規則：

- **`scanners._ux_fake_buttons`**（新增於 `analyze_ux`）：原始 HTML 的 `<div>`／`<span>`／`<li>` 掛 `onclick` 但**完全沒有 `role` 屬性**（`_FAKE_BUTTON_RE`）→ `ux-fake-button`（LOW、category UX）。這類假按鈕對螢幕報讀者唸不出、鍵盤 Tab 不到、AI 代理從可及性樹也看不到。
- **保守避免誤報**：只要元素帶了 `role=`（作者已有意識處理語意）就不列入；真 `<button>`／`<a>` 不列入；沒有 onclick 的一般 `<div>` 不列入。與 axe 的 button-name（看「有沒有名稱」）互補、不重複。
- 只讀已保存 HTML、不需量測、零額外請求；證據為標籤片段（截斷、不含值），最多 8 個。
- 測試：`tests_fake_button.py`（6）。
- 文件：`docs/scan-stage-checks.md`（UX 表）、`backend/apps/scans/CLAUDE.md`（UX 三來源段）、競賽需求書 UX 段同步。

## 原因
使用者審查 claude-seo plugin 後，從中挑這一項（相較「內容品質/AI 生成偵測」誤報風險低、判定確定性高、補 Argus 空白、呼應「AI agent 時代頁面可操作性」定位）。axe-core 檢查按鈕「有沒有名稱」，但看不到「根本不是按鈕（div onclick）」這個更根本的問題。

## 影響範圍
- 勾 UX 的掃描，頁面若有 div／span 假按鈕會多一項 LOW finding；接既有 `page_ux` 覆蓋，無新檢查登記。
- 當天規則集變更，`RULESET_VERSION` 維持當日版本。

## 驗證方式
- `tests_fake_button`（6）＋ accuracy_review／axe／mobile_layout／scoring／report 回歸共 67 項通過；`ruff check backend` 通過。
- 誤報防護已鎖測試：真 `<button>`／`<a>` 不報、`<div role=button>` 不報、無 onclick 的 `<div>` 不報。
