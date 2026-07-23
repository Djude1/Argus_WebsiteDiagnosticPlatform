# K8s Kali SQLmap 實作計畫

**日期**：2026-07-14

**操作者**：Codex

## 變更內容

- 新增 K8s Kali SQLmap Job 的逐步 TDD 實作計畫。
- 將核准規格狀態更新為「計畫已完成、尚未執行」並加入雙向文件入口。
- 在 K8s README 補上實作計畫連結。

## 原因

現有 Docker exec 攻擊鏈無法在 containerd Kubernetes 正式環境運作；核准設計需要轉成可由後續實作者逐 task 執行、驗證、review 與回復的文件，同時維持 Secret at-rest encryption 完成前禁止啟用的硬門檻。

## 影響範圍

- 本次只有文件變更，不修改 backend、runner、Kubernetes manifest、CI 或正式叢集。
- 計畫涵蓋共用政策、AI 優先、runner、RBAC／admission／NetworkPolicy、image promotion、隔離整合測試、加密門檻與正式 rollout。
- Metasploit、Nmap、多 Job 排程等核准的非目標仍保留在後續工作清單。

## 驗證方式

- PASS：對照核准規格逐節檢查，11 個 task 涵蓋政策、executor、runner、AI、K8s、CI、整合、文件、加密與 rollout。
- PASS：Task 編號為 1 至 11，138 個 Markdown fence 成對，沒有截斷或禁止 placeholder。
- PASS：本次四份文件的 Markdown 相對連結皆存在，未發現 stale status、私鑰或常見 token pattern。
- PASS：git diff --check 無 whitespace error；本次未執行 backend 測試，因為沒有修改程式碼或 manifest。
