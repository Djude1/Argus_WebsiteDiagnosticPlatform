# 修復 /team 去識別化誤混入既有 WIP 樣式導致全站跑版

**日期**：2026-08-04
**操作者**：Claude

## 變更內容

- 將 `styles.css` 與 `PublicPages.jsx` 恢復到 push 前的乾淨 origin 基底，再只重新套用 `/team` 去識別化修改。
- 移除誤混入的 topology v2 全站樣式；該批樣式約 850 行，並讓正式 CSS 出現 56 個 `topology-panel` selector。
- 由修復 commit `a8859a5` 回復正式版面，去識別化內容維持不變。

## 原因

前次去識別化 commit `8a1f508` 將共用樣式與公開頁元件整檔加入 stage，連帶納入工作區原本尚未完成的 topology v2 修改，導致正式環境 dashboard 與 `/team` 跑版。這違反 `argus-git-safety`「只 stage 本次改動」的規則。

## 影響範圍

- 正式環境 dashboard 與 `/team` 的版面由 `a8859a5` 恢復。
- `/team` 去識別化效果保留，不重新加入已移除的識別欄位。
- 本次修復沒有修改後端資料模型、API 契約或 K8s 設定。

## 驗證方式

- 本機 frontend production build 通過。
- 正式 CSS 的 `topology-panel` selector 數量由 56 降為 1，確認誤混入樣式已移除。
- 公開團隊 API 不再回傳不應公開的識別欄位，4 筆團隊展示資料均通過欄位檢查；本記錄不列出個別帳號或聯絡資訊。

## 後續規則

- 共用樣式或大型元件在 stage 前必須先檢查完整 diff。
- 工作區混有其他未完成內容時，使用逐 hunk stage，避免整檔納入無關修改。
