# 重構 CLAUDE.md：將特定需求資訊拆到 docs/ 子文件

**日期**：2026-06-03  
**操作者**：Claude

## 變更內容

- 精簡 `CLAUDE.md`（453 行 → 約 290 行），保留每次都需要的核心資訊
- 新增 `docs/` 子文件，存放特定情境才需要查閱的詳細說明：
  - `docs/log-template.md` — log 記錄格式範本
  - `docs/doc-sync-rules.md` — 文件同步詳細規則 A/B/C + 接手文件清單
  - `docs/md-checklist.md` — MD 修改強制核對清單
  - `docs/cloudflared-guide.md` — cloudflared 雙路徑陷阱 + 跨 zone DNS 地雷（同時修復截斷 bug）
  - `docs/rtk-guide.md` — RTK 使用規則
  - `docs/node22-guide.md` — Node 22 portable 詳細安裝說明
- `CLAUDE.md` 末尾新增「特定操作指南」索引表，指向各 docs/ 文件
- 同時修復 git HEAD 的 CLAUDE.md 截斷 bug（cloudflared 段落 step 3 以後全部遺失）

## 原因

使用者反映 CLAUDE.md 資訊過多，每次對話都載入大量只有特定需求才用到的內容（cloudflared 操作、RTK 規則、詳細文件同步條款等），希望保持核心精簡、特定需求時再查閱對應文件。

## 影響範圍

- `CLAUDE.md` 是每次對話都載入的 context，精簡後減少 token 用量
- 行為準則 1-6、禁止事項清單、常用命令、路由地圖、Model 速查等核心規則**完整保留**
- `docs/` 目錄新增 6 個文件，需納入 git 追蹤

## 驗證方式

- 確認 CLAUDE.md 中所有 `docs/` 連結對應的檔案均已建立
- 確認禁止事項清單、行為準則、常用命令內容完整保留
- 確認 cloudflared 完整 4 步驟已在 docs/cloudflared-guide.md 中（修復截斷）
