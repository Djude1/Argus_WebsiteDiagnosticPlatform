---
allowed-tools: Read, Edit, Write
description: 對話結束前必做：更新 MD/idea.md 記錄本次決策，並確認 MEMORY.md 索引
---

## 這個 skill 的使用時機

- 對話結束前（**不能只說「記得更新」，必須實際寫入**）
- 新功能實作完成
- 有重要決策或地雷被發現

---

## ⚠️ SKILL 同步（每次對話都必做，不可省略）

**凡是本次對話有改動以下內容，必須同步更新對應 SKILL 檔**：

| 改動類型 | 必須更新的 SKILL |
|---------|----------------|
| 啟動指令、Port、模組職責異動 | `/arch`（`.claude/commands/arch.md`）|
| YOLO 模型換檔、新增 PT | `/arch` 的「YOLO 模型分工」|
| APP 語音流程、TTS 地雷 | `/arch` 的「Android APP 語音架構」|
| API 金鑰測試方式改變 | `/api-check`（`.claude/commands/api-check.md`）|
| 修改前確認流程 | `/check`（`.claude/commands/check.md`）|
| 刪除流程 | `/delete`（`.claude/commands/delete.md`）|
| commit 禁止項目 | `/pre-commit`（`.claude/commands/pre-commit.md`）|

**做法**：直接 Edit 對應的 `.claude/commands/*.md`，不能只更新 MEMORY.md。

SKILL 是 Claude 每次對話的「工作手冊」，情報不同步 = 下次對話必定犯同樣錯誤。

---

## ⚠️ 交接資料同步（每次改動必做）

凡是修改了以下檔案，**對話結束前必須同步一份到 `_交接資料/`**：

| 修改的檔案 | 同步指令 |
|-----------|---------|
| `.env` | `cp .env _交接資料/.env` |
| `Website/.env` | `cp Website/.env _交接資料/Website.env` |
| `google_Speech_to_Text.json` | `cp google_Speech_to_Text.json _交接資料/` |
| `Google_Api_Key.json` | `cp Google_Api_Key.json _交接資料/` |

同步後若有模型路徑或功能說明異動，一併更新 `_交接資料/README.md`。

> `_交接資料/` 是給別人接手時用的，只放 GitHub 上沒有的機密設定。內容過時 = 別人無法正確啟動系統。

---

## 步驟 1：更新 MD/idea.md

**寫入格式**（加在對應功能的段落，或新增段落）：

```markdown
## 功能名稱（狀態：已實作 / 已修復 / 待實作，日期）

### 決策重點
- 決定了什麼、為什麼這樣做

### 涉及檔案
- `檔案名.py`：改了什麼

### 注意事項（可選）
- 已知地雷、限制、未來要注意的點
```

**狀態標記規則**：
- `已實作`：功能完成且測試通過
- `已修復`：Bug 修復完成
- `待實作`：計劃中但尚未開始
- `進行中`：開始但尚未完成

---

## 步驟 2：確認 MEMORY.md 索引

```bash
cat C:/Users/USER/.claude/projects/D--GitHub-Project-Fork-OpenAIglasses-for-Navigation/memory/MEMORY.md
```

若有新的重要決策、偏好改變、或架構異動，同步更新對應的 memory 檔案。

---

## 步驟 3：確認沒有遺漏

對照本次對話，逐項確認：
- [ ] 新功能 → 寫進「已實作」
- [ ] Bug 修復 → 寫進「已修復」，記錄根本原因
- [ ] 刪除的檔案 → 更新「專案清理紀錄」表格
- [ ] 發現的地雷 → 加進「已知限制與地雷」
- [ ] 架構決策 → 更新 MEMORY.md 的架構摘要

---

## 不需要寫進 MD 的內容

- 測試輸出（只記結果，不記 log）
- 暫時性的工作狀態（只記最終決策）
- 已在程式碼中顯而易見的事
