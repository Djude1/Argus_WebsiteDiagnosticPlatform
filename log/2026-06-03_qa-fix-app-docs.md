# QA 鐵則入規則 + 子代理審查修正 6 份 app 文件

**日期**：2026-06-03
**操作者**：Claude

## 變更內容
- **`CLAUDE.md`**：新增「品質保證（QA）鐵則：假設一定有問題，去找出來」段落（內容 QA + 佔位符 grep + fresh-eyes 子代理）；Skills 表格補上 `argus-project`（Codex 用、Claude 不自動載入）以對齊 `專案導覽.md`。
- **依新 QA 鐵則派子代理 fresh-eyes 審查**本次新增文件，找到 13 個問題，**親自對照程式碼驗證後**修正 9 個文件不實/不一致處：
  - `agent/CLAUDE.md`：ToolExecutor 工具清單由 4 個補正為實際 8 個（click/type_text/scroll/get_visible_text/get_dom_summary/take_screenshot/report_ux_issue/finish）；`ARGUS_AGENT_ENABLED` 大小寫對齊。
  - `accounts/CLAUDE.md`：`me/` PATCH 釐清為僅可改 first_name/last_name。
  - `reviews/CLAUDE.md`：rating「僅建立時可設」補註 admin 可經 `admin_api.reply_review` 校正（寫 audit `rating_override`）；image 驗證改為「目前未實作（待補）」。
  - `content/CLAUDE.md`：據實改為「`TeamMemberSerializer` 公開輸出含 email/github_url（團隊自介刻意公開）」；禁止項改為終端使用者個資。
  - `insights/CLAUDE.md`：標明 `analyze_speed` 的 redirect SSRF 殘留（`allow_redirects=True` 未對 final host 重檢）為「待修」。
  - `專案導覽.md`：修正第五節對「本檔第二節」的張冠李戴引用。

## ⚠️ 留給使用者裁決的「真實程式碼問題」（本次只改文件、未改程式碼）
1. **🔴 insights `analyze_speed` SSRF 殘留**：`backend/apps/insights/analyzers.py:251-259` 用 `allow_redirects=True`，只對原始 URL 做 `assert_public_url`，未對 redirect 後 `response.url` 重檢 → 公開 URL 若 302 轉內網仍會被抓。屬線上真實風險，建議修（redirect 後重檢 final host 或 `allow_redirects=False` 逐跳檢）。
2. **🟠 content 公開 API 輸出團隊 email**：`content/serializers.py` `TeamMemberSerializer` 含 `email`/`github_url`，`team_list` 為 `AllowAny`。**疑似刻意**（團隊頁聯絡資訊），請確認是否要保留。
3. **🟡 程式碼註解小錯（非文件）**：`accounts/views.py` `GoogleLoginView` docstring 寫 `/admin/`（應為 `/django-admin/`）；`admin_api/models.py` docstring 提到的 `admin_adjust`/`reply_review` 非實際 action 值。

## 影響範圍
- 純文件變更；新增 QA 鐵則會讓之後修改都走「假設有錯→子代理 fresh-eyes」流程。
- 上述 3 個程式碼問題**未改動**，待使用者決定。
- 本次只 commit、不 push。

## 驗證方式
- 子代理（general-purpose）獨立審查 + 我親自 Read 對照 `tools.py` / `content/serializers.py` / `insights/analyzers.py` / `admin_api/views.py:391` / `reviews/serializers.py` 確認每項屬實再改。
- 修正落地複驗全數命中；佔位符掃描唯一命中為 QA 規則自身的舉例文字（誤判），實際 0 殘留。
