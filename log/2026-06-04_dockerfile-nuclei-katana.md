# Dockerfile 加入 Nuclei + Katana binary 安裝

**日期**：2026-06-04
**操作者**：Claude

## 變更內容

- 修改 `Dockerfile`：在 Python/Playwright base image 中新增安裝步驟
  - apt 安裝 `unzip`、`wget`
  - 從 GitHub releases 下載 `nuclei_3.8.0_linux_amd64.zip` 並安裝到 `/usr/local/bin/`
  - 從 GitHub releases 下載 `katana_1.1.2_linux_amd64.zip` 並安裝到 `/usr/local/bin/`
  - 執行 `nuclei -update-templates` 預先下載 templates（加速首次掃描）
  - 使用 `ARG NUCLEI_VERSION` / `ARG KATANA_VERSION` 固定版本，方便未來升級

## 原因

Docker worker 容器執行 Celery 掃描任務，但先前未安裝 nuclei/katana binary，導致 `shutil.which()` 回傳 None，Nuclei/Katana 掃描靜默略過（silent-fail）。需在 image 內預裝 binary 才能讓 Docker 部署享有完整資安掃描能力。

## 影響範圍

- Docker worker 容器現在可執行完整 Nuclei + Katana 掃描
- 免費模式（passive）：log 顯示「Nuclei（快速免費）」
- 付費模式（active + authorized）：log 顯示「Nuclei（深度付費）」
- Docker image build 時間增加約 2-3 分鐘（下載 binary + templates）

## 驗證方式

- `docker exec argus-worker-1 nuclei -version` → `v3.8.0` ✅
- `docker exec argus-worker-1 katana -version` → 正常輸出 ✅
- 透過 Argus UI（localhost:8080）建立掃描：
  - passive 掃描（#15）：log 顯示「Nuclei（快速免費）」，完成 ✅
  - active+authorized 掃描（#14）：log 顯示「Nuclei（深度付費）」，完成 ✅

## 教訓：整合測試一律用 Docker，不用本機 runserver

**問題**：本次驗證最初嘗試用 `uv run python manage.py runserver` 本機開發環境，導致：
- Celery 需要 Redis broker，本機未安裝 Redis → `RuntimeError: Retry limit exceeded`
- Playwright browser 路徑不一致（`.ms-playwright` vs 全域路徑）
- `monthly_limit` 前端/後端版本不同步導致 crash
- 需要繞過 UI 改用 Django shell 直接呼叫 task
- 浪費大量時間安裝 Node 22、嘗試 build 前端

**正確做法**：掃描功能整合測試一律使用 Docker 環境（`localhost:8080`）：
```powershell
# 1. 確認 Docker 已啟動
docker compose ps

# 2. 若程式碼有改動，重建 worker（含 nuclei/katana）
docker compose up -d --build web worker

# 3. 給測試帳號補充 coin
docker exec argus-web-1 uv run python manage.py shell -c "..."

# 4. 開啟 localhost:8080 透過 UI 測試
```

Docker 環境包含完整 Redis、Celery worker、nginx、前端 dist，與正式部署完全一致，不需要額外安裝任何工具。
