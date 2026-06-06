# 進一步精簡 CLAUDE.md：架構速查改為子模組索引

**日期**：2026-06-03  
**操作者**：Claude

## 變更內容

- `CLAUDE.md` 架構段落從 130+ 行壓縮至 15 行，改為 4 行索引表
- 新建 `backend/CLAUDE.md`（86 行），包含：後端 API 路由地圖、8 個 App 職責邊界、關鍵 Model 速查（5 個 Model）、三種管理介面
- 擴充 `frontend/CLAUDE.md`，新增前端路由地圖（21 條路由）與核心檔案表

## 原因

前端路由地圖、後端 API 路由地圖、Model 速查等內容只有在「要修改那個模組」時才需要查閱，與路標一樣只需索引，詳細內容放在對應的子目錄 CLAUDE.md。

## 影響範圍

- CLAUDE.md：373 行 → 249 行（再減 33%）
- 需要查前端路由 → 看 `frontend/CLAUDE.md`
- 需要查後端 API / Model / App 職責 → 看 `backend/CLAUDE.md`

## 驗證方式

- CLAUDE.md 中所有子 CLAUDE.md 連結均有對應實體檔案
- 核心規則（禁止事項、行為準則、常用命令）完整保留
