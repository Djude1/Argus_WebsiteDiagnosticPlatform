# 2026-06-04 前端 Evidence 面板

## 任務

在前端 Finding 詳情加入「查看證據」能力，讓初審 Demo 可直接展示 Deterministic Evidence 與 Evidence-first 架構。

## 已完成

- 在 `frontend/src/App.jsx` 新增 `EvidencePanel`。
- Finding 詳情卡新增：
  - Deterministic Evidence 標題。
  - 規則 ID。
  - 證據來源。
  - 證據型態。
  - Evidence 文字。
  - Evidence JSON。
  - AI 解釋與改善建議區塊。
  - 複製 Evidence 按鈕。
- 在 `frontend/src/styles.css` 新增 Evidence 面板樣式，避免長網址與 JSON 撐破右側欄位。

## 驗證

- `npm install`
- `npm run build`

## 備註

`npm install` 僅在 `frontend` 目錄修復本地 `node_modules`，未安裝全域套件。過程中 npm 回報部分舊 `.bin` 暫存 shim 清理失敗的權限警告，但安裝成功且 `npm run build` 通過。

