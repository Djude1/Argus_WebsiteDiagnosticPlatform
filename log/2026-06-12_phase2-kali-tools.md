# 2026-06-12 Phase 2 kali_tools + Phase 1 docker-compose kali（初審後衝刺）

## 變更內容

- **新增** `backend/apps/scans/security/kali_tools.py`
  - `run_sqlmap(target_url, scan_job_id)`、`run_metasploit(module, options, scan_job_id)`
  - 三重授權鎖：`ARGUS_KALI_ENABLED` + `scan_mode=active` + `active_testing_authorized`
  - container 運行檢查、命令注入防護（list 形式 + 輸入驗證）、silent-fail、append_log
- **新增** `backend/apps/scans/tests_kali_tools.py`（12 項單元測試，mock subprocess）
- **修改** `backend/config/settings.py`：新增 `ARGUS_KALI_ENABLED` / `ARGUS_KALI_CONTAINER` / `ARGUS_KALI_TIMEOUT`
- **修改** `docker-compose.yml`：新增 `kali` 服務（`profiles: [attack]`，預設不啟動）
- **同步文件**：`security/CLAUDE.md`（kali_tools 待建→已建 + 三重鎖說明）、`docs/capstone-roadmap.md`（加進度快照，修正 Phase 4 實為已完成）

## 原因

初審結束，依 `docs/capstone-roadmap.md` 繼續未完成項目。盤點發現 Phase 4（Nessus 差距補齊）
實際早已完成（文件漂移誤標「尚未開始」），真正待建的是 Phase 1-3 Kali 攻擊鏈，其中
`kali_tools.py` 是唯一可純程式碼完成且可單元測試的部分。

## 影響範圍

- 預設零影響：`ARGUS_KALI_ENABLED` 預設 False、kali 服務 `--profile attack` 隔離、
  `tasks.py` 尚未呼叫 kali_tools，現有掃描/部署流程完全不變。
- 啟用攻擊鏈仍需手動 infra（worker 掛 docker.sock + 裝 docker CLI），屬授權隔離環境才套用。

## 驗證方式

- `uv run python backend/manage.py test apps.scans.tests_kali_tools` → 12 passed OK
- `uv run python backend/manage.py test apps.scans.tests_security_scanners` → 38 passed OK
- `uv run python backend/manage.py check` → no issues
- `uv run ruff check`（新檔 + settings）→ All checks passed
- `docker compose config` → OK

## 待人工驗證（無法自動測試）

1. Mint 機部署 DVWA / Metasploitable 2 靶機
2. `docker compose --profile attack up -d kali` 實際拉起 kali container
3. worker 掛載 docker.sock 後，端到端跑通「Nuclei 偵測 → kali_tools 驗證」攻擊鏈

---

## 追加（同日，第二段）：接進 worker 正式流程

使用者已 `docker compose --profile attack up -d kali`（sqlmap/msf/nmap 裝好），
靶機 `https://htb.xn--gst.tw/`（CTF「宇宙錯誤知識管理局」）運行中、Kali 已驗證可連通。
依使用者選擇「接進 worker 正式流程」，把攻擊鏈接進掃描 pipeline：

### 追加變更
- **kali_tools.py**：新增編排層 `validate_findings_with_kali(scan_job_id, candidate_urls)`，
  挑帶 query 參數 URL 跑 sqlmap，確認注入才產 `kali-sqlmap-sqli` critical Finding；
  `_stdout_indicates_sqli` 判定（**不可用 "injectable" 當特徵**，會誤中否定句，測試已抓到並修正）
- **owasp_mapper.py**：`kali-sqlmap-sqli` → (A03, CWE-89)
- **tasks.py**：nuclei 後、`deep_mode` 時呼叫 `validate_findings_with_kali`，silent-fail，寫回 Finding
- **Dockerfile**：worker image 加 docker CLI 靜態 binary（27.3.1，僅 client）
- **docker-compose.attack.yml**（新）：override worker 加 docker.sock 掛載 + `ARGUS_KALI_ENABLED=true`；
  **刻意不放進基礎 compose**，避免公網生產 worker 取得 host root 權限
- 文件同步：security/CLAUDE.md（已接進流程）、capstone-roadmap.md（進度）

### 追加驗證
- `test apps.scans.tests_kali_tools apps.scans.tests_security_scanners` → 56 passed OK
- `manage.py check` → no issues；`ruff check` → All checks passed
- `docker compose config`（base）→ OK；`-f ... -f docker-compose.attack.yml --profile attack config`
  → 正確注入 docker.sock + ARGUS_KALI_ENABLED + argus-kali-1

### 仍待人工（需在場授權，分類器會 gate 主動攻擊）
- `docker compose -f docker-compose.yml -f docker-compose.attack.yml --profile attack up -d --build`
  重建 worker
- 跑一次 active + authorized 掃描打靶機，確認 sqlmap finding 端到端寫回
