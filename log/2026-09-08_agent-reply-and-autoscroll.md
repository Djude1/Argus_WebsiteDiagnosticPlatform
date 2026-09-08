# Agent 回覆可讀性、思考流自動捲動、system prompt 重寫

**日期**：2026-09-08
**操作者**：Claude

## 變更內容

### ① 思考流自動捲動（前端）
`RebuildWorkspace.jsx`。三個 bug 疊在一起：

1. **依賴項用 `trace.length`**——後端把連續推理合併進同一則，agent 在想的時候
   陣列長度一直是 1，effect 根本不會重跑。改用內容總長度
2. `scrollIntoView` 會連帶捲動祖先容器。改成直接設 `scrollTop`（AIWM 的做法）
3. 在 DOM 更新**後**才算「離底部多遠」會誤判：內容剛長大、距離自然變遠，
   於是判定成「使用者捲上去了」而停止跟隨。改用 `onScroll` 記錄使用者意圖

順帶修掉一個會讓元件直接崩潰的 TDZ：`traceSignature` 原本宣告在使用它的
effect 之後。

### ② 回覆只有 JSON
- `prompts.py`：要求兩段——先三到六句白話說明（改了什麼、**哪些沒處理及原因**、
  有疑慮的地方），再給 ```json 區塊
- `services.py`：新增 `_human_reply()`，顯示用的 reply 剝掉所有程式碼區塊

### ③ agent system prompt（`.126` 上，不在 repo 內）
整份重寫。工具從「read/write/edit/glob/grep 開啟」改為**全部關閉**。

## 原因

使用者回報三點：思考流沒有自動向下滑動、「分析 Agent 的回復只有 Json 沒有
任何說明，對於一個成熟的項目這太怪了」、以及要求優化 system prompt。

第二點的根因在 system prompt 自己：

```
5. 完成後只回覆一行摘要，不要把整份 HTML 貼在回覆裡。
你沒有執行指令的能力…唯一的產出方式是用 write 工具寫檔。
```

**它叫 agent 只回一行**，而請求端又要求輸出 JSON——兩者相加，回覆就只剩那塊
JSON。而且整份 prompt 還停留在「寫檔」時代，與現行架構（模型只輸出修改清單）
完全不符。

## 影響範圍

- `.126` 的 agent 設定**需要重啟才生效**（`sudo systemctl restart opencode`）
- 工具全關是這輪最大的安全收斂：改成修改清單後 agent 完全不需要碰檔案系統，
  現在它就是個純文字模型
- 只有 JSON 沒有說明時 `reply` 會是空字串，前端顯示「這一輪沒有文字回覆」
  ——比顯示一坨 JSON 誠實

## 驗證方式

- `apps.rebuild` 67 tests OK（新增 `HumanReplyTests` 4 項）
- ruff / check 通過；前端 `vite build` 通過

## 未驗證（需使用者）

- **新 system prompt 的實際效果**：`.126` 尚未重啟，載入的仍是舊設定
  （查 `GET /agent` 確認 write/read 仍為 allow）
- 前端自動捲動的行為無法在開發機自動驗證
