# Nuclei 整合（fast/deep 雙模式資安掃描）

**日期**：2026-06-04
**操作者**：Claude

## 變更內容

- 新增 `backend/apps/scans/nuclei_scanner.py`：Nuclei binary 封裝，支援 fast（精選模板，6 分鐘）與 deep（全部模板，12 分鐘）雙模式
- 新增 `backend/apps/scans/tests_nuclei_scanner.py`：8 個單元測試（binary 缺失、fast/deep 旗標、JSONL 解析、severity mapping、去重、timeout、畸形 JSON）
- 修改 `backend/apps/scans/katana_scanner.py`：從 Docker 執行改為本機 binary，以 `shutil.which("katana")` 偵測，移除 Docker 依賴
- 修改 `backend/apps/scans/tasks.py`：以 `ThreadPoolExecutor(max_workers=2)` 並行執行 Katana + Nuclei；加入 `deep_mode`（`scan_mode=active AND active_testing_authorized`）；移除 `active_probes` 呼叫；補強 `.result()` 錯誤處理
- 刪除 `backend/apps/scans/active_probes.py`：由 Nuclei 取代（admin 路徑枚舉、開放目錄、SQLi boolean 均被 Nuclei 模板覆蓋）
- 刪除 `backend/apps/scans/tests_active_probes.py`
- 更新 `backend/apps/scans/CLAUDE.md`：新增 nuclei_scanner.py 模組說明，移除 active_probes 引用
- 新增設計文件 `docs/superpowers/specs/2026-06-03-nuclei-integration-design.md`
- 新增實作計畫 `docs/superpowers/plans/2026-06-03-nuclei-integration.md`

## 原因

原有 active_probes.py 僅涵蓋 3 類主動探測（admin 路徑、開放目錄、SQLi boolean），缺乏 XSS、CORS、CVE、JWT、SSRF 等主流漏洞類別。引入 Nuclei（29k stars，ProjectDiscovery）後可大幅提升資安偵測廣度，同時以 binary 取代 Docker 加速啟動。付費使用者（active + authorized）可觸發全模板深度掃描。

## 影響範圍

- 掃描流程：scanning 主迴圈後的 Katana + Nuclei 並行執行，取代原有順序執行 + active_probes
- 免費掃描（passive）：新增 Nuclei 精選模板偵測，Finding 數量預期增加
- 付費掃描（active + authorized）：Nuclei 全模板掃描，Finding 數量顯著增加
- Docker 依賴移除：katana_scanner 不再需要 Docker，開發環境更輕量
- 破壞性變更：`active_probes.py` 已刪除，任何直接引用此模組的程式碼需更新

## 驗證方式

- 單元測試：`uv run python backend/manage.py test apps.scans` → **112 tests OK**
- ruff lint：`All checks passed!`
- Django system check：`0 issues`
- 手動整合驗證（Task 6）：需安裝 Nuclei/Katana binary 後對靶機執行，見計畫文件
