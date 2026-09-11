# 票05：報告頁「修正產出」專區 UI

**日期**：2026-09-11  
**操作者**：Claude（ZCode）

## 變更內容
- `frontend/src/components/scans/FixOutputSection.jsx`（新元件）：修正產出專區——「產生修正內容」按鈕觸發 `/fix-output/trigger/`、3 秒輪詢狀態（產生中→完成／失敗含原因）、ready 後載入產物；四分頁（JSON-LD／OG＋meta／llms.txt／FAQ Schema，FAQ 無產物時自動缺頁）、每個程式碼區塊一鍵複製（已複製 ✓ 回饋）、llms.txt blob 下載、逐欄位來源標註面板（verified=已驗證來源綠／**placeholder=請人工確認 amber 警示**／rule／extracted／partial，附來源頁連結）；失敗可重新產生。
- `frontend/src/features/scans/ScanExperience.jsx`：`FindingsWorkspace` 主 grid 之後全寬掛載 `FixOutputSection`，**只在 `scan.status === "completed"` 時 render**（進行中的掃描沒有完整事實基礎，也不該誤觸計費）。
- `frontend/src/styles.css`：`.fixoutput-*` 樣式（跟隨 rebuild-box 卡片語言；placeholder 警示色與 verified 對比）。
- 文件同步：frontend/CLAUDE.md 核心檔案表。
- 附註：`frontend/node_modules` 原本不存在，以 portable Node 22 的 `D:/nodejs/npm.cmd install` 安裝既有 package.json 相依（未新增套件）。

## 原因
spec 票 05（`.scratch/fix-output/issues/05`）：報告的行動價值要接到「能修問題」——專區讓管理者對照 finding 逐項採用可貼上產出；「已產出重看不重算、重複複製不計費」由冪等 API（票04）保證，UI 只在 idle/failed 顯示觸發按鈕。

## 影響範圍
- 僅掃描完成後的報告頁多一個專區；進行中／失敗掃描、其他頁面不受影響。
- 功能後端預設關閉：trigger 會收到 503 並顯示「無法觸發」訊息。

## 驗證方式
- 前端 build：`cd frontend ; .\build-node22.ps1` 成功（25.2s，所有 chunk < 500KB）。
- 後端無程式碼變更（票04 全綠狀態維持）。
- **需手動驗證清單**（repo 無 JS 測試基建，依 spec 以手動清單處理）：
  1. 完成掃描的報告頁出現「修正產出」專區；進行中的掃描不出現。
  2. `ARGUS_FIXGEN_ENABLED=true` 環境下按「產生修正內容」→ 狀態徽章「產生中」脈動 → 完成後出現四分頁。
  3. 每分頁一鍵複製貼入文字編輯器內容一致；llms.txt 下載檔可開、內容與分頁相同。
  4. 佔位符【請填寫：…】欄位在來源標註面板顯示 amber「請人工確認」。
  5. 重新整理頁面後 ready 產出仍在（重看不重算、不重複計費）；失敗時顯示原因且按鈕變「重新產生」。
  6. 功能關閉環境（預設）按鈕顯示錯誤訊息而非無反應。
