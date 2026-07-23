# K8s Kali SQLmap Job 設計規格

**日期**：2026-07-14

**操作者**：Codex

## 變更內容

- 新增 K8s SQLmap Job 的設計規格，涵蓋 AI 優先、規則式 fallback、三重授權鎖、全域單工、
  短效 Secret、RBAC、admission、NetworkPolicy、錯誤、取消、清理與測試。
- 將 Metasploit、Nmap、專用 Controller、多 Job 併發與非同步 completion 明列為後續工作。
- 記錄正式 Kubernetes 1.35.6、containerd、現有 worker RBAC／NetworkPolicy 與 Secret at-rest
  encryption 尚未啟用的證據邊界。

## 原因

原有 `docker exec argus-kali-1` 只能在隔離 Compose demo 使用；正式 K8s 使用 containerd，且
沒有 Kali workload、Docker daemon、工具、啟用設定或 Job RBAC。使用者希望先完成可審閱的
修復文件，並確認必須保留 Hermes-Agent 自主呼叫 SQLmap 的產品目標。

## 影響範圍

- 本次只新增設計與交接文件，不修改 backend、K8s manifest、叢集或正式服務。
- 規格把 Secret at-rest encryption 設為啟用 Kali Kubernetes backend 的硬門檻。
- 正式實作前仍需使用者審閱規格，再另寫逐步 implementation plan。

## 驗證方式

- 對照 `kali_tools.py`、`agent/tools.py`、`agent/runner.py`、`tasks.py`、settings、Compose attack
  override 與 K8s manifests，確認現行兩個 SQLmap 入口與缺少的 infra。
- 正式叢集唯讀確認 Kubernetes 1.35.6、containerd 2.2.5、worker 使用 default SA 且無 Job／
  Pod log 權限、API Service／endpoint、Calico CNI 與 encryption provider 未設定。
- 參考 Kubernetes 官方 Python client、Job／TTL、ValidatingAdmissionPolicy 與 data-at-rest
  encryption 文件確認設計能力與版本相容性。
- 文件完成後執行 placeholder、矛盾、連結、敏感資訊與 `git diff --check` 檢查。
