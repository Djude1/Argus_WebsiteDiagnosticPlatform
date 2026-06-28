# Node 22 Portable 使用說明

系統 Node 是 v24.13（`C:\Program Files\nodejs`），但 v24 + Rollup 4.x 在 Windows 會 crash（`STATUS_STACK_BUFFER_OVERRUN`，exit `-1073740791`）。已將 Node v22 解壓到 portable 目錄（不動 PATH 也不動系統 Node）。

## 實際路徑（2026-06-14 確認）

本機已有兩份 portable Node 22：
- `D:\nodejs` — v22.17.0（**主要使用**）
- `D:\Node` — v22.14.0（備援）

`frontend/build-node22.ps1` 會依序 probe `D:\nodejs` → `D:\node22` → `D:\Node`，第一個有 `node.exe` 的勝出，所以**路徑不是寫死**。

> 歷史備註：CLAUDE.md 與舊文件常寫 `D:\node22`，那是早期路徑；目前實際在 `D:\nodejs`。新環境裝在哪個都能跑（只要有 `node.exe`）。

## 各情境使用方式

| 情境 | 做法 |
|---|---|
| **build**（最常用） | `cd frontend ; .\build-node22.ps1`（script 會自動 probe Node 22 位置） |
| **dev server** | `npm.cmd run dev`（兩種 Node 都能跑，dev 不經 Rollup 打包） |
| **重灌 node_modules** | `cd frontend ; D:\nodejs\npm.cmd install`（或 D:\Node、D:\node22 看哪個存在）|

## 安裝方式（未安裝環境）

1. 下載 `https://nodejs.org/dist/latest-v22.x/node-v22.22.3-win-x64.zip`
2. 解壓到 `D:\nodejs`（或 `D:\node22`、`D:\Node` 任一，build script 都能找到）
3. 不需要 admin 權限，也不需要改環境變數

完成後確認：`D:\nodejs\node.exe --version` 應輸出 `v22.x`。
