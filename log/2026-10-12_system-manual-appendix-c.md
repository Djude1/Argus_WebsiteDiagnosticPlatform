# 系統手冊：掃描階段與檢測項目（9-2 總表＋附錄三）

**日期**：2026-10-12  
**操作者**：Claude

## 變更內容
- 新增 `專題文件生成/系統手冊_附錄三_掃描階段與檢測項目.md`，含兩段可直接貼進課程系統手冊 docx 的內容：
  - 9-2 補充段落：表 9-2-3 掃描階段總表，列出 17 個階段的執行條件與是否連線受測網站
  - 附錄三全文：由 `docs/scan-stage-checks.md` 精簡，表號 C-1～C-15
- 附錄三補上原檔沒寫的事實：
  - 資安發現的四種類型與 OWASP Top 10:2025／CWE 對照
  - 被動 API 檢查與 API 端點清單（資安分析頁、PDF 附錄），以及「不讀原始碼、不代表全部 API」的限制
  - Nuclei 版本鎖定與每月更新比對
- `Word文件同步規則.md`、`專題文件生成/CLAUDE.md`、`docs/scan-stage-checks.md` 標註這份精簡版，原檔改了要一起同步

## 原因
使用者審查課程系統手冊（停在 86e1250，10/5）時，決定把掃描檢測說明完整放進手冊：
- 回應評審「定期更新 OWASP 規則」「能否檢測後端程式或 API」
- 回應評審「釐清範圍」，說明哪些階段會連到受測網站

依手冊固定章節結構，做成附錄三，不另開一章。

## 影響範圍
- 只新增文件，不改程式
- 尚未套進 docx，需人工貼上或另行套用

## 驗證方式
- 嚴重度權重（60／35／12／4／0）、衰減常數 100、頁數 50／深度 6、OWASP 2025 由 2021 對照推導、每月工具更新 workflow：對照 `scanners.py`、`settings.py`、`security/owasp_mapper.py`、`.github/workflows/scanner-update-check.yml` 確認
- 其餘判定標準沿用 `docs/scan-stage-checks.md`（2026-10-12 已同步觸控目標與 SRI 規則）

## 補充（同日）：附錄三加入 AI Agent 工具範圍與管控
- C-18 新增表 C-16（工具分類與提供條件）、表 C-17（安全管控：同網站限制、導覽限制、不破壞資料、嚴重度上限、遮罩、離線知識庫、預算、總開關）
- 只寫用途與管控，不寫工具參數與測試手法細節
- 修正工具數量文件漂移：程式 `TOOL_SCHEMAS` 為 25 個（`backend/CLAUDE.md` 原寫 20、`backend/apps/agent/CLAUDE.md` 原寫 26）
- 驗證：對照 `agent/tools.py`（`build_tool_schemas` 的 deep_only 與 `allow_form_submit`、同源檢查、replay 方法限制）、`agent/CLAUDE.md` 安全硬規則、`settings.py` 的步數／token 上限

## 補充（同日）：附錄三不列 OWASP ZAP、系統手冊依程式現況修訂
- 附錄三 md 移除 OWASP ZAP 被動分析：預設關閉（`ARGUS_ZAP_ENABLED=false`），正式環境未部署 `k8s/optional/zap-passive.yaml`。表 9-2-3 改為十六個階段並重新編號，C-14～C-21 改為 C-13～C-20
- 系統手冊 docx 另依程式現況修訂。docx 不在 repo，交付給使用者：
  - 修正產出畫面（10/6 移除）與授權勾選（10/8 移除）的描述
  - 側欄改為「掃描與報告」「資安分析」
  - 資料字典補 12 個欄位（462）
  - API 表補 `/api/verify/` 等端點
  - 10-3 加入 AEO 回歸資料集量測：60 站、82 題，`manage.py aeo_benchmark` 全數通過
  - 附錄二回答改為指向附錄三
  - 表2-1-1 版本、4-2 分組數、表A-1，以及 4 個簡體字
