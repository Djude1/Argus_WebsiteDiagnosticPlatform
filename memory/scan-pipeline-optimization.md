# 2026-07 掃描範圍與效能治理

## 範圍

修正掃描編排把「單頁」誤當可執行整站工具的問題，並縮短 Playwright、Nuclei、Katana 與敏感路徑探測的無上限等待。

## 核心決策

- 產品掃描範圍只有單頁與全網站；`passive/active` 是探測授權層級，不是第三種範圍。
- 既有資料模型未設 `scope` 欄位，因此以 `max_pages=1` 表示單頁，其餘合法值表示全網站；決策集中於 `scan_plan.py`。
- passive 不執行 Nuclei、Katana、敏感路徑探測、Hermes-Agent 或 Kali。
- active+authorized 單頁只執行輸入頁 Nuclei 與既有 Kali 同源候選驗證；不啟動任何整站探索。
- active+authorized 全網站才執行 Katana、已爬 URL 的 Nuclei、敏感路徑探測與 Agent；Kali 維持後段、不可與 Nuclei 同時打目標。
- Katana/Nuclei 共享全域主動 RPS；1 RPS 時依序執行，2 RPS 以上才平分預算並行。
- crawler 不等待容易被長連線拖住的 `networkidle`；Katana 加 45 秒爬取上限、2 MiB 回應上限、同主機範圍與 query 去重；Nuclei 只保留 medium 以上並設 5 分鐘硬上限。
- exposure scanner 重用 crawler 的 robots 結果，移除重複 robots 與 sitemap I/O；sitemap 的公開頁面清單不再被當作敏感路徑逐一探測。
- 外部工具 finding 與 scan log 在持久化前統一遮罩 URL query、PII、extracted raw 值與短 secret；Nuclei 禁用公共 OAST、限制 HTTP protocol 與 private network。
- Playwright 主 frame navigation、WebSocket 與 Katana exact-origin scope 不得跨出使用者授權 origin；CDN 子資源仍可依 public HTTP policy 載入。
- Nuclei/Katana 改用可取消 process runner；取消或 timeout 時對 POSIX process group 先送 `SIGTERM`、一秒後送 `SIGKILL`，`ScanCancelled` 原樣交回 tasks 的取消／退款分支。
- exposure probe 不得以一般例外吞掉 `ScanCancelled`；必須立即停止、進入取消與退款，不再繼續 Agent、Kali 或計分。
- 建立掃描 API 必須先回 `201 + queued + ScanJob.id`，不可因本機 Celery eager 而在 request 內同步跑完整掃描；eager 僅透過 DEBUG web process 內「單 worker、單 outstanding」背景 executor 管理獨立 Python 掃描程序，避免 Windows Playwright 在 web thread 建立事件迴圈時偶發 `WinError 10013`。子程序使用 `apply(throw=True)`，父程序負責硬逾時、process-tree 清理、DB connection 清理與非終態任務冪等退款；`scans.E001` 守住正式環境誤設邊界，正式環境仍使用 broker/worker。
- 掃描前估價只依使用者選擇的頁數上限與 billing 單價回傳預扣上限，不連線、解析 DNS 或讀取目標網站；真正抓到的頁數於完成後結算並退回差額。

## 驗證與限制

- 執行計畫、Celery 編排、Nuclei/Katana 命令預算、evidence 遮罩、process 取消、同源 route 與 exposure pacer 已有回歸測試。
- Linux-only 測試會建立忽略 `SIGTERM` 的 descendant，確認整個 process group 最終不再執行；Windows 本機只驗證訊號升級順序，Linux CI/K8s 必須實跑該測試。
- 本機 eager 的立即導頁不代表任務具持久性；runserver 重啟可能中斷，完整背景鏈路仍須用 Docker Redis/Celery/PostgreSQL 驗證。
- 本機 eager 掃描使用既有已授權單頁任務複製、交易回滾與暫存 media 驗證，未留下測試資料。
- Docker Desktop 當時不可用，因此 Redis、正式 Celery worker、PostgreSQL 與容器內真實 Nuclei/Katana 的完整整合仍須另做。
