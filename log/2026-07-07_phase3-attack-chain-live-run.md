# Phase 3 Nuclei→Kali sqlmap 攻擊鏈端到端實跑驗證

**日期**：2026-07-07  
**操作者**：Claude（使用者現場授權，目標為自有站點）

## 變更內容
- 本次為**執行驗證 + 文件同步**，無程式碼邏輯變更。
- 重新補回遺失的本機 `.env`（從桌面同名專案 `C:/Users/ntub/Desktop/Argus/.env` 複製；含真實密鑰，未提交）。
- 疊 `docker-compose.attack.yml` 拉起 stack；因既有 `argus-kali-1`（另一 project）撞名，改**不加 `--profile attack`**、複用既有 kali container（worker 仍取得 socket 掛載 + `ARGUS_KALI_ENABLED=true`）。
- 文件同步：
  - `docs/capstone-roadmap.md`：Phase 3 由「⏳ 待實跑」→「✅ 端到端已實跑驗證」；快照日期 2026-06-23→2026-07-07。
  - `docs/nessus-gap-analysis.md`：攻擊鏈備註「待實機 demo 收尾」→「已實跑驗證」。

## 原因
roadmap Phase 3 唯一剩餘驗收條件為「重建 worker 後跑一次 active+authorized 掃描驗證端到端」。使用者要求接續完成，並確認 `aiglasses.qzz.io` 為自有站點、授權主動測試。

## 影響範圍
- 純驗證 + 文件；不動 scanner / 狀態機 / billing 邏輯，無迴歸風險。
- 證實攻擊鏈 infra（worker → host docker.sock → `docker exec argus-kali-1` → sqlmap）在真實外網目標可用。
- `.env` 為本機機密檔（git 不追蹤），勿提交。

## 驗證方式
- 以 `APIClient.force_authenticate(1124)` 打真正的 `POST /api/scans/`（active + `active_testing_authorized`），走完整 view→serializer→扣點→`run_scan_job.delay`→celery worker 自主 pipeline。
- scan #1 `scan_log` 佐證鏈路：爬取 10 頁（含 `/purchase?product=1`）→ `Nuclei 完成（深度（付費））` → `Kali sqlmap 開始驗證：aiglasses.qzz.io` → `完成（returncode=0）` → 掃描完成、85 findings。
- kali `/tmp/sqlmap/aiglasses.qzz.io/target.txt` 記錄實際指令：`sqlmap -u https://aiglasses.qzz.io/purchase?product=1 --batch --output-dir=/tmp/sqlmap`。
- 結果：sqlmap 判**無可注入點**（`log`、結果 CSV 皆空），故**正確未**產生 `kali-sqlmap-sqli`（無假陽性）——攻擊鏈機制正常，僅此目標不可注入。
- 待人工/後續驗證：如需展示 positive SQLi critical finding，需對刻意易受攻擊靶機（如 `htb.xn--gst.tw`）另行授權實跑。
