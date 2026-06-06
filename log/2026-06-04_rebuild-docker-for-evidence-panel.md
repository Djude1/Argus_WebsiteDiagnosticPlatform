# 2026-06-04 Docker 重建 Evidence 面板

## 問題

使用者執行 `docker compose up` 後沒有看到前端 Evidence 面板變化。

## 原因

- `frontend`、`web`、`worker` 服務皆使用 Docker image，不是 bind mount 原始碼。
- 單純執行 `docker compose up` 會沿用既有 image，不會重新打包前端 `dist` 或後端程式碼。
- 首次重建時 `frontend` build context 包含本機 `node_modules`，其中 npm 產生的 Windows 暫存 `.bin` shim 導致 Docker build context 讀取失敗。

## 處理

- 新增 `frontend/.dockerignore`，排除：
  - `node_modules`
  - `dist`
  - `.vite`
  - npm/yarn/pnpm debug log
  - 本地 env 覆寫檔
- 執行：
  - `docker compose up -d --build web worker frontend`
- 確認：
  - frontend image 內 JS 已包含 `Deterministic Evidence`。
  - web image 內已有 `rule_id` 欄位與 `0007_finding_evidence_first_fields.py` migration。
  - `showmigrations scans` 顯示 `0007` 已套用。

## 備註

舊掃描資料是在 Evidence-first 欄位加入前產生，可能沒有 `rule_id` 與 `evidence_json`。若要展示完整 Evidence-first 面板，建議重新建立一筆掃描任務。

