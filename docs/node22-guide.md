# Node 22 Portable 使用說明

系統 Node 是 v24.x（`C:\Program Files\nodejs`，2026-07-07 實測 v24.14.1），但 v24 + Rollup 4.x 在 Windows 會 crash（`STATUS_STACK_BUFFER_OVERRUN`，exit `-1073740791`）。做法是把 Node v22 解壓到 portable 目錄（不動 PATH 也不動系統 Node），build 一律走該 portable Node。

## 路徑（build-node22.ps1 自動偵測，非寫死）

`frontend/build-node22.ps1` 會依序 probe `D:\nodejs` → `D:\node22` → `D:\Node`，第一個有 `node.exe` 的勝出，所以**路徑不是寫死**——新環境把 portable Node 22 裝在這三個任一即可（見下方「安裝方式」），三個都沒有時 script 會報 `No portable Node 22 found` 並中止。

> ⚠ 現況（2026-07-07 實測）：本機三個候選路徑目前**都沒有** portable Node 22，系統只有 Node v24.14.1。**首次 build 前必須先依下方「安裝方式」裝一份 Node 22**，否則 `build-node22.ps1` 會直接失敗。
>
> 歷史備註：CLAUDE.md 與舊接手文件常寫死 `D:\node22`，那是早期路徑；一律以 build-node22.ps1 的自動偵測結果為準，不要在文件裡寫死任何一個路徑。

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
