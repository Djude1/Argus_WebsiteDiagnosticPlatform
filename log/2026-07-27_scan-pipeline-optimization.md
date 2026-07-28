# 掃描流程範圍與效能最佳化

**日期**：2026-07-27<br>
**操作者**：Codex

## 變更內容

- 新增 `scan_plan.py`，集中產生單頁／全網站及 active 授權的工具執行計畫。
- `tasks.py` 依執行計畫編排：passive 不跑主動工具；active 單頁只跑輸入頁 Nuclei 與既有 Kali 驗證；active 全網站才跑 Katana、整站 Nuclei、敏感路徑探測與 Agent。
- Katana/Nuclei 共享 `ARGUS_ACTIVE_MAX_RPS`；1 RPS 改為依序執行，避免並行流量超額。
- crawler 移除每頁 `networkidle` 額外等待；Katana/Nuclei 加入明確時間、速率、並行、範圍與資源預算。
- exposure scanner 重用 crawler 的 robots 結果，移除重複 robots/sitemap 抓取與 sitemap 全頁探測。
- 依獨立安全審查補上 finding/log 持久化前遮罩：Nuclei query/extracted raw、exposure PII、Katana 短 secret 均不再原樣保存。
- Nuclei 加入 private network、OAST、HTTP protocol、危險 tag、response size 與授權 User-Agent 限制；Katana 加 exact-origin scope 與授權 User-Agent。
- 新增可取消的外部 process runner；取消/timeout 會對 POSIX process group 先送 `SIGTERM`、寬限後送 `SIGKILL`，並讓 `ScanCancelled` 立即回到既有取消與退款分支。
- Playwright 在送出前阻擋跨 origin 的主 frame navigation 與 WebSocket；exposure 的 baseline/正式 probe 共用同一 RPS pacer。
- 新增與調整執行矩陣、外部工具命令及 exposure scanner 回歸測試；同步模組規則、能力文件與專案記憶。

## 原因

單頁掃描過去仍會啟動 Katana 整站探索、Nuclei、敏感路徑字典及其他後段工具，造成使用者只選一頁卻等待很久；全網站流程也缺少跨工具總 RPS 與硬時間預算。

## 影響範圍

- 影響 Celery 掃描編排、Playwright 等待策略、Nuclei/Katana subprocess 參數與敏感路徑探測。
- Finding/API/報告不再取得外部工具回傳的原始 query value、extracted value、PII 片段或短 secret；保留風險類型、數量與遮罩後位置供修復。
- 不新增前端模式、不修改 API schema、Model、migration、計費或 ScanJob 狀態機。
- Nuclei 僅保留 medium/high/critical 模板，優先回報可行動風險；單頁不再取得整站 Katana 技術棧與敏感路徑結果。
- Docker Desktop 不可用，容器內真實 binary 與完整 Redis/Celery/PostgreSQL 鏈路仍待可用環境複驗。

## 驗證方式

- `uv run ruff check`（相關 Python 檔）：pass。
- `uv run python backend/manage.py check`：pass。
- `uv run python backend/manage.py makemigrations --check --dry-run`：pass，無 model 漂移。
- 掃描執行計畫、Nuclei/Katana、exposure scanner targeted tests：pass。
- `uv run python backend/manage.py test apps.scans`：441 項 pass、2 項 skip（含 1 項僅在 Linux 執行的 process tree 整合測試）。
- `uv run python backend/manage.py test apps`：627 項 pass、2 項 skip。
- 獨立安全複查：Critical 0、High 0、Medium 0。
- 本機 eager active 單頁 smoke：交易回滾、暫存 media；確認未執行 Katana 與 exposure，任務約 17 秒完成。
