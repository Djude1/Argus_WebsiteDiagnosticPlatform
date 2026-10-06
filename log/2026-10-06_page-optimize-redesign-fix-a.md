# 頁面優化失敗（agent 思考 5 分鐘後「沒有提出任何修改」）與側邊欄完全固定

**日期**：2026-10-06
**操作者**：Claude

## 變更內容

### 優化失敗
- `rebuild/services.py`
  - 回覆解析逐層容錯：```json 圍欄 → 無圍欄或圍欄沒收尾時，從 `{"summary"`／`{"edits"` 解析 → 仍失敗就逐筆救回完整的修改（`_salvage_payload`）。另外容許字串內直接換行（`strict=False`）。
  - visual 修改改為只給 `css`，由系統包成 `<style data-argus="類別">` 加在 `</head>` 前；`category` 只接受白名單值。
  - `apply_edits` 拒絕 `css` 含 `<` 的修改，避免用 `</style>` 跳出去插入 HTML。
  - `_no_edits_reason` 區分四種原因：撞到輸出上限（`finish=length`）、只有思考沒有輸出、格式無法解析、真的沒有修改。
  - `_human_reply` 也剝掉沒收尾的圍欄。
- `rebuild/client.py`：`session_result` 回傳最後一個 step 的 `finish`。
- `rebuild/prompts.py`、`docs/opencode-agents/argus-rebuild.md`
  - JSON 放在回覆最前面，說明放後面。
  - 視覺改善 3–6 項，只寫 `css`，CSS 字串用單引號。
  - 思考保持精簡，不在思考中先寫出 CSS／JSON 草稿；整份回覆約 6000 字元，寧可少幾項也要把 JSON 寫完。
- 前端
  - 成果頁失敗時顯示 agent 的說明與思考過程（不能追問）。
  - 「頁面」分頁的失敗列加「查看過程」。

### 側邊欄
- `legacy-member/93-projects.css`：側邊欄高度固定為導覽列以下到主內容底部內距之間，本身不捲動。
- 依螢幕高度收合：
  - <900px：拿掉小字說明
  - <780px：精簡方案卡
  - <680px：隱藏方案卡
  - 只有 <520px 才退回內部捲動
- 收合規則放在檔尾；第一版放在前面，被後面的基本規則蓋掉，實測沒有生效。

## 原因
- **優化失敗**：使用者對 ntubimdbirc.tw 首頁優化，agent 思考約 5 分鐘後失敗並退點。舊的解析方式只要整段 JSON 有一點問題就整批丟掉：
  - 輸出被截斷時沒有收尾圍欄，找不到 JSON；
  - 備用解析只認 `{"edits"` 開頭，但新格式以 `summary` 開頭；
  - 視覺修改要在 JSON 字串裡手寫 `<style data-argus=\"…\">`，引號跳脫很容易出錯。
- **注意**：無法取得正式環境該筆的 `finish` 與回覆內容，確切是哪一種失敗未能確認。這次的修正四種情況都涵蓋，下次失敗時錯誤訊息會直接說明原因。
- **側邊欄**：使用者要求側邊欄完全固定、不能捲動。實測側邊欄高 774px，在 1536×730 只有約 600px 可用，所以出現內部捲動；捲到頁底時還會被外框往上推 8px。

## 影響範圍
- **部署後必須同步 agent 主機的定義檔**（`docs/opencode-agents/argus-rebuild.md` → `~/.config/opencode/agent/argus-rebuild.md`，再 `sudo systemctl restart opencode`），否則 agent 仍用舊格式。舊格式（visual 用 find/replace）仍相容。
- 無 migration。

## 驗證方式
- `uv run python backend/manage.py test apps.rebuild`：101 項 OK，新增：
  - css 包裝、category 無法撐破屬性、css 含 `<` 被拒
  - 無圍欄以 summary 開頭、截斷保留完整的修改、單筆壞掉不影響其他筆、字串內換行
  - 失敗原因、未收尾圍欄的說明剝除
  - 截斷回覆仍交付
- `uv run ruff check backend`：通過（第一次 push 漏了一個 E501，後續 commit 修正）。
- 前端 lint、typecheck、218 項測試、build 皆通過。
- **側邊欄（Playwright）**：
  - 1920×937、1536×730、1440×789、1366×657、1280×600、1280×560：內容高度等於可視高度，沒有內部捲動。
  - 捲到頁底時 top 維持 100px（修正前 92px）。
  - 1280×500 為退回捲動的極矮情境。
- 失敗頁截圖確認：顯示錯誤原因與思考過程，沒有追問表單，沒有 JS 錯誤。
- **需人工確認**：正式環境以真實 agent 重新優化 ntubimdbirc.tw 首頁。

## 追加：側邊欄功能項目均勻攤開
- 使用者回饋：收合後項目擠在上方，方案卡上面留下一片空白。
- `93-projects.css`：≥1024px 時 `.project-sidebar-nav` 改為 flex 直排，佔滿剩餘高度，`justify-content: space-around`；項目高度不變，空間平均分到項目之間。移除高度 <680px 時頁尾的 `margin-top: auto`（改由選單填滿）。
- 驗證（Playwright）：1920×1080、1920×937、1536×730、1440×789、1366×657、1280×600、1280×560 皆無內部捲動，捲到頁底 top 維持 100px；截圖確認項目間距平均、沒有大片留白；前端 lint 通過、build 成功。
