# Juice Shop 本機測試環境與自主測試能力 baseline

**日期**：2026-09-25
**操作者**：ZCode（GLM-5.3）

## 變更內容

1. **私網目標旁路開關**（掃本機 Docker 網路內靶機的前提）：
   - `backend/config/settings.py`：新增 `ARGUS_ALLOW_PRIVATE_TARGETS`（預設 false）與 `ARGUS_NUCLEI_DEEP_TIMEOUT`（預設 300）
   - `backend/apps/scans/services.py`：`allow_private_targets()`（runtime 強制 DEBUG 雙條件）；`assert_public_http_url`／`resolve_public_host_ips` 於旁路放行私網、localhost、單標籤 hostname、非標準 port（userinfo／無法解析仍拒）
   - `backend/apps/scans/domain_verification.py`：`normalize_domain` 於旁路放行單標籤／IP／localhost（網域驗證閘門可對 Docker 服務名操作）
   - `backend/apps/scans/checks.py`：新增 `scans.E002`（非 DEBUG 開旁路即部署檢查錯誤）
   - `backend/apps/scans/nuclei_scanner.py`：`-lna`（= `-restrict-local-network-access`，nuclei 內建私網封鎖）改為「非旁路才加」；deep 逾時改讀 `ARGUS_NUCLEI_DEEP_TIMEOUT`
2. **`docker-compose.juice.yml`**（新增，受控 demo overlay）：Juice Shop 容器＋web/worker 疊加 DEBUG＋旁路＋`ARGUS_AGENT_ENABLED=true`（與 K8s 正式一致）＋demo 調幅（Agent tokens 150k、Nuclei 900s）
3. **MiniMax 模型升級**：`backend/apps/agent/providers.py` `default_model` `MiniMax-M2.7` → `MiniMax-M3`（2026-06 發佈；同價、同 OpenAI 相容 API、SWE-bench Verified 56.2→80.5）
4. **`docs/competitive-positioning.md`**（新增）：vs 工具編排型 VAPT 對手、vs DefectDojo 的定位論述＋Juice Shop benchmark 方法論＋三輪實測數據
5. **文件同步**：`.env.example` 新鍵、`backend/apps/scans/CLAUDE.md`（`-lna` 語義更正＋旁路小節）、`docs/environment-preflight.md`（Juice Shop 環境段落）

## 原因

使用者要在與對手（整合 GitHub 經典工具的 VAPT 專案）比較前，先以 OWASP
Juice Shop 靶機建立可重現的自主測試能力 baseline：本地環境功能面必須與 K8s
正式環境一致（Agent 開啟、完整 Celery 鏈）。既有公開目標政策（SSRF 防護）
會擋掉所有私網目標，故以「DEBUG 雙條件＋部署檢查」的受控旁路解鎖，正式
環境安全邊界不變。同時完成 MiniMax 最新模型調研與升級。

## 影響範圍

- 正式環境（K8s／非 DEBUG）：行為完全不變（旁路不可能生效；`-lna` 照加；300s 逾時不變）
- 本機 demo：可掃 `http://juice-shop:3000`；主動掃描仍需 VerifiedDomain（走 admin override 正式流程）
- Nuclei 深掃逾時可調（環境變數），正式預設維持 300s
- Agent 主力模型改為 MiniMax-M3（token 用量實測與 M2.7 相當，63k/20 步）

## 驗證方式

- 單元測試：`apps.scans.tests_private_target_bypass`（23 項新測試）＋ `tests_nuclei_scanner` ＋ `tests_domain_verification` 全過；`apps.scans` 全套 724 項中 72 個 ERROR 均為本機 Windows 缺 CJK 字型的既有環境限制（stash 驗證與本次改動無關；Docker 容器內有 fonts-noto-cjk）
- 整合實測（Docker 完整堆疊＝db/redis/web/worker/frontend/juice-shop/kali 全 healthy）：
  - 掃描 #9：旁路生效（目標接受）、Agent 爆 60k token 上限（發現 M3 用量問題）
  - 掃描 #10：`-lna` 移除後 Nuclei 真的執行但 300s 不足（超時略過）；Agent 17 步完整完成
  - 掃描 #11（最終，900s＋Kali docker backend）：16 findings（2 高/7 中/5 低/2 資訊）、**Agent 回報 3 個 UX findings（M2.7 兩輪皆 0）**、Kali sqlmap 對 3 target 實際執行（首頁無 query 參數故 confirmed=False）、總分 65
  - 報告：16 頁 Word 下載 OK；`/api/verify/` 防偽查驗 `matches=True`；視覺驗收 16/16 頁 pass（圖表 CJK 正常、色塊一致、數字自洽）
- 樣本留存：`log_assets_juice/`（掃描 #10/#11 報告 docx、#11 PDF、16 頁 PNG）

## 已知限制與後續建議

- Juice Shop 為 Angular SPA，BFS 爬蟲僅得 2 個唯一 URL → Nuclei/sqlmap 有效輸入面受限（黑盒本質限制）。建議後續開發「掃描 seed URL」功能讓使用者餵關鍵 API 端點
- Nuclei 全模板在 2 RPS 下需 50+ 分鐘，900s 內必然截斷（保護目標站的取捨，維持）
- demo 帳號僅存在於本機 demo DB（demo-admin@argus.local / juice-tester@argus.local，密碼僅容器內有效，不影響正式環境）
