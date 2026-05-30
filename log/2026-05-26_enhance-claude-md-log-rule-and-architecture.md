# 強化 CLAUDE.md：加入 log 規則與完整架構地圖

**日期**：2026-05-26  
**操作者**：Claude

## 變更內容
- `CLAUDE.md`：新增「任務完成記錄規則（log 資料夾）」段落，規範 log 檔命名格式、Markdown 模板與注意事項
- `CLAUDE.md`：在「專案架構」下新增三個子節：
  - 前端路由地圖（React Router 全路由表 + 核心檔案對照）
  - 後端 API 路由地圖（URL 前綴 → Django App → 主要端點）
  - 關鍵 Model 速查（ScanJob 狀態機、CoinWallet、CoinTransaction、AdminAuditLog、PlatformReview）
- `log/.gitkeep`：建立 log 資料夾並追蹤進 git
- `CLAUDE.md`：在準則 5（目標導向執行）新增「強成功條件 vs 弱成功條件」說明（來自 Karpathy CLAUDE.md）

## 原因
組員修改了大量內容但未留下詳細記錄，導致難以追蹤「誰動了什麼、為什麼動」。同時 CLAUDE.md 缺乏前端路由與後端 API 的對照表，每次定位修改位置需要手動 grep。

## 影響範圍
- 所有後續任務完成後均需在 `log/` 補記錄
- 架構說明為靜態快照，若新增路由或 Model 需同步更新 CLAUDE.md

## 驗證方式
- 讀取更新後的 CLAUDE.md 確認格式正確
- 確認 `log/.gitkeep` 存在，資料夾已建立
