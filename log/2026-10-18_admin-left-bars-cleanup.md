# 後台樣式：補清殘留的彩色左邊條（2026-10-18）

## 背景
使用者要展示後台給評審，要求後台也升級優化。逐檔審閱後台樣式（`18`、`20`、`22`、`32`、`62`、`72`
號檔與 `components/admin/*`）後確認：後台已是 Night Watch `--admin-*` token 化的同一套設計系統
（深淺主題自動、骨架／空／錯誤狀態、動效克制）。真正的落差是 **4 處違反全站規則
「禁用彩色左邊條」**（2026-10-04 的清理漏掉，CSS 註解還寫著「左側虹膜指示條」「左側色條」）。

## 變更（`frontend/src/styles/18-admin.css`）
1. 側欄選中項 `.admin-nav-link.active::before` 的 3px 虹膜條 → 移除；選中只留柔青底＋細框＋圖示轉色。
2. 可點表格列 hover／focus 時 `td:first-child` 的 `inset 3px 0 0` 虹膜條 → 移除；hover 底色與 focus 外框保留。
3. 被檢舉評論卡 `.admin-review.is-reported` 的 `inset 3px` 紅條 → 整圈紅框（`--admin-tone-bad-border`）＋ 5% 淡底。
4. 掃描詳情維度分數卡 `.admin-cat-score-item::before` 的 3px 維度色條 → 移除；維度色改用在標籤徽章
   （`.admin-cat-score-label`：14% 色底、文字與主文字色 72% 混合，與 `--admin-tone-*-text` 同做法確保日間可讀）。
   順手移除只為 `::before` 存在的 `position: relative; overflow: hidden`。

## 文件
- `frontend/CLAUDE.md` 全站禁用左邊條規則：補 2026-10-18 清理項目。

## 驗證
- `npm run lint`、`npm run typecheck`、`npx vitest run`（見 commit 當下輸出）。
- 無法在雲端環境渲染畫面；請使用者實機確認：側欄選中項、掃描列表 hover、評論治理被檢舉卡、
  掃描詳情維度分數卡（深／淺主題各看一次）。

## 未完成／待使用者指示
使用者所指「後台沒升級優化」可能是（a）正式站仍跑舊版前端（本 session 先前已確認正式站落後 repo）、
或（b）對特定頁面有具體不滿。本次只修可驗證的規則落差，不做看不到畫面的主觀改版；需使用者指名頁面或截圖。
