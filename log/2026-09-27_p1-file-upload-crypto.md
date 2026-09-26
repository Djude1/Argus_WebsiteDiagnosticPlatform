# P1 第二批：multipart 上傳＋file_upload 角色＋crypto 角色與 forge_jwt

**日期**：2026-09-27
**操作者**：ZCode（GLM-5.3）

## 變更內容
- `backend/apps/agent/tools.py`：
  - replay_request 新增 `files` 參數（≤2 檔；multipart/form-data；檔名≤120、
    內容≤8000 純文字探測）；`redact_tool_arguments` 對 files 白名單化
    （field/filename/content_type/content_length，內容不持久化）
  - 新增 `forge_jwt`（第 23 工具，deep_only＋runtime 再驗）：本地偽造——
    alg=none 無簽；HS256 內建 10 個常見弱密鑰（jwt_tool/rockyou 精選）
    各簽一組；token 交回 agent 以 replay 驗證接受度
- `backend/apps/agent/runner.py`：新增兩角色（6→8）：
  - `file_upload`（WSTG-BUSL-08）：副檔名繞過（大小寫/雙副檔名/空位元組）、
    content-type 淺改、filename 穿越、大小邊界；**上傳後驗證**（GET 路徑
    匿名直讀＝高風險）
  - `crypto`（PortSwigger JWT/jwt_tool 方法論）：簽章接受度四路（alg=none/
    弱密鑰/竄改沿用原簽/過期）＋token 敏感欄位＋可預測隨機值
- 文件同步：架構文件（23 工具＋8 角色表）、agent CLAUDE.md

## 原因
P1 缺口分析：檔案類 6 挑戰與密碼學 8 挑戰全空白（無工具無角色）。
泛化紅線（使用者指示）：全部提示詞錨定 OWASP WSTG／PortSwigger 教材／
jwt_tool 通用方法論與業界 payload 慣例——零目標特定路徑/參數/答案。

## 影響範圍
- deep_mode 掃描多 2 specialist＋2 工具；passive 不受影響
- replay files 僅純文字探測內容（非執行檔本體）

## 驗證方式
- apps.agent 60 tests OK（新 4：forge_jwt 三案例＋files redact）；ruff 通過
- #39 輪測（rebuild 後）以 scoreboard_diff 量測差集驗收
