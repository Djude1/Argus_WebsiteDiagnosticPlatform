# Node 22 Portable 使用說明

系統 Node 是 v24.13（`C:\Program Files\nodejs`），但 v24 + Rollup 4.x 在 Windows 會 crash（`STATUS_STACK_BUFFER_OVERRUN`，exit `-1073740791`）。已將 Node v22.22.3 解壓到 `D:\node22`（portable，未動 PATH 也未動系統 Node）。

## 各情境使用方式

| 情境 | 做法 |
|---|---|
| **build**（最常用） | `frontend/build-node22.ps1`（已自動切 `D:\node22` 走完 build） |
| **dev server** | `npm.cmd run dev`（兩種 Node 都能跑，dev 不經 Rollup 打包） |
| **重灌 node_modules** | `D:\node22\npm.cmd install` |

## 安裝方式（未安裝環境）

1. 下載 `https://nodejs.org/dist/latest-v22.x/node-v22.22.3-win-x64.zip`
2. 解壓到 `D:\node22`
3. 不需要 admin 權限，也不需要改環境變數

完成後確認：`D:\node22\node.exe --version` 應輸出 `v22.22.3`。
