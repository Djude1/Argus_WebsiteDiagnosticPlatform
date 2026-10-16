# Celery worker 明確設定併發數與預取數

**日期**：2026-10-16  
**操作者**：Claude

## 變更內容
- `k8s/04-backend.yaml`：worker 啟動指令加上 `--concurrency=2`、`--prefetch-multiplier=1`，附註原因。
- `tests/test_k8s_runtime_commands.py`：新增 `test_worker_concurrency_is_bounded`，鎖定這兩個參數。
- `k8s/README.md`：檔案表的副本數更正為 web／worker／frontend 各 ×3，並註明 worker 併發與全叢集上限。

## 原因
使用者新增一台 K8s 節點，web、worker、frontend 與 NGINX Gateway 副本由 2 改為 3（`1e9dd4a`、`254970f`、`0aa880a`）。檢查時發現 worker 啟動指令沒有指定併發數。

- **未設併發數**：Celery 會依節點 CPU 核心數開子程序，每個子程序同時跑一個掃描、各帶一個 Chromium。核心多的節點可能同時開很多瀏覽器，撐爆 3Gi 記憶體上限（OOMKilled 會讓掃描卡在進行中，只能等 reaper 回收）。
- **預取預設 4**：限制併發後，一個 worker 可能先保留 8 個掃描慢慢做，其他 worker 閒置。

## 影響範圍
- 全叢集同時最多 6 個掃描（3 worker × 2），超過的排在 Redis 佇列等候，不會失敗。
- 啟動指令改變會讓 Argo 滾動更新 worker；`terminationGracePeriodSeconds` 照舊讓進行中的掃描跑完。
- 本機 `docker-compose.yml` 的 worker 未改（開發用，單一容器）。

## 驗證方式
- 在最新 `origin/main`（`0aa880a`）上修改。
- 依 CI 順序：
  - ruff 通過
  - `tests/` 36 項通過（新測試在舊設定下失敗、新設定下通過）
  - `manage.py check` 通過
  - `verify_rendered_manifests.sh` 通過（kubectl v1.31）
  - 後端全套 1931 項通過（skipped 12）
- 尚未在正式叢集驗證：
  - worker 滾動更新完成
  - `celery inspect stats` 顯示 `max-concurrency: 2`
  - 同時送出多個掃描時平均分到不同 worker
