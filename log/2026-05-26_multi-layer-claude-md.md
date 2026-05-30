# 建立多層 CLAUDE.md 架構

**日期**：2026-05-26  
**操作者**：Claude

## 變更內容
- `CLAUDE.md`：新增「多層 CLAUDE.md 架構」說明表格（四層：使用者層、專案層、子目錄層、個人覆寫層）
- `CLAUDE.md`：新增「禁止事項清單」表格（10 條明確禁止操作 + 原因 + 正確做法）
- `frontend/CLAUDE.md`：新建，涵蓋 App.jsx 操作規範、build 規則、狀態管理、樣式、元件新增、套件安裝
- `backend/apps/billing/CLAUDE.md`：新建，涵蓋唯一入口原則、services.py 函式一覽、冪等機制、transaction type 枚舉
- `backend/apps/scans/CLAUDE.md`：新建，涵蓋狀態機流程、各檔案職責、progress JSON 格式、合作式取消、Playwright 規則
- `CLAUDE.local.md`：新建個人覆寫層範本（不提交）
- `.gitignore`：加入 `CLAUDE.local.md`

## 原因
參考 Medium 文章《CLAUDE.md 完全攻略》，實作三層 + 隱藏第四層架構。
原本所有規則集中在一個 CLAUDE.md，組員無法快速找到模組專屬規則（如 billing 的唯一入口、scans 的狀態機）。

## 影響範圍
- 所有後續對話：Claude 操作 `frontend/`、`billing/`、`scans/` 時會自動載入對應子目錄 CLAUDE.md
- 不影響現有程式碼邏輯，純文件變更

## 驗證方式
- 確認四個 CLAUDE.md 檔案均已建立且格式正確
- 確認 `.gitignore` 已新增 `CLAUDE.local.md`
- 手動確認各子目錄 CLAUDE.md 的規則與程式碼實際行為一致
