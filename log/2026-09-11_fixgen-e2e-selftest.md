# E2E 實機自主測試：修正產出全流程（真實 MiniMax LLM）

**日期**：2026-09-11  
**操作者**：Claude（ZCode，瀏覽器控制＋本機 eager 模式）

## 變更內容（測試發現的兩個實際 bug 修復）
- `backend/apps/scans/fixgen/engine.py`
  - `parse_llm_json` 先剝除 `<think>…</think>` 區塊再找 JSON 邊界：推理型模型（實測 MiniMax-M2.7）回應前綴思考文字，其中含 JSON 範例的 `{`，舊邊界抓取把完整可用的正式輸出判成解析失敗。
  - `generate_artifacts` 傳遞 `timeout=settings.ARGUS_FIXGEN_TIMEOUT`。
- `backend/apps/agent/providers.py`：`chat_text`／`chat_with_tools` 全鏈加入選填 `timeout` 參數（預設仍 `DEFAULT_TIMEOUT=60`，不影響 Hermes 既有行為）。實測 MiniMax-M2.7 對真實 fixgen prompt（約 2k 字元）推理＋輸出需 **76.8 秒**，超過 60 秒導致 chain 落到本機不可用的 GLM（讀逾時）／Gemini（403）。
- `backend/config/settings.py`：`ARGUS_FIXGEN_TIMEOUT`（預設 180 秒）。
- `backend/apps/scans/tests_fixgen.py`：FakeProvider 記錄 kwargs；新增 2 個回歸測試（think 剝除、逾時傳遞）。

## 原因
使用者要求以 subagent＋瀏覽器控制自主完成票05/06 的手動驗證清單。實機跑真實 LLM 鏈路時發現上述兩個只會在真實 provider 上出現的問題（假 provider 測試覆蓋不到推理前綴與網路逾時）。

## 影響範圍
- 僅 fixgen 引擎與 provider 選填參數；Hermes agent 行為不變（timeout 預設值相同）。
- 本機環境事实：LLM 主力僅 MiniMax（GLM 未包含於本機、Gemini 403）——chain 順序 MiniMax 為首， fallback 在本機不會被觸及，無需設定變更。

## 驗證方式（本機 eager runserver + IAB 瀏覽器控制）
- **票05 清單**：登入→完成掃描 `/scans/1` 有專區✓；進行中 `/scans/2` 無專區✓；觸發→真實 MiniMax 產生→「已完成」✓；四分頁（JSON-LD／OG＋meta／llms.txt／FAQ Schema）內容逐頁檢查✓（全為爬取事實：電話/地址/社群/圖片/FAQ 問答）；欄位來源標註（已驗證來源＋來源頁連結、規則產生）✓；一鍵複製在此瀏覽器環境剪貼簿被拒→優雅顯示「複製失敗，請手動選取」（成功路徑回饋於沙箱限制下無法驗證）；llms.txt 下載事件觸發✓；重整後仍已完成、無重新產生按鈕（不重複計費）✓；失敗狀態顯示原因與「重新產生」✓；功能關閉（無旗標重啟）顯示「修正產出功能目前未開放。」✓。
- **票06 清單**：quick-scan（example.com）結果卡下方導流區塊「完整掃描可獲得可直接貼上的修正內容」＋登入按鈕✓。
- **DB 帳目**：餘額 500→470；交易軌跡 `fixgen_charge -30 → 失敗 fixgen_refund +30 → 重試 fixgen_charge -30`（真實 LLM 失敗下驗證全額退點）；FixOutput ready／provider=minimax／model=MiniMax-M2.7／tokens=4464。
- **測試**：`apps.scans.tests_fixgen apps.agent` 56 tests OK；`ruff check` 通過。
- 測試資料留在本機 dev DB（fixgen-e2e 帳號、scan 1–3，網域 sunshine.example／disabled.example），需要時可自行刪除。
