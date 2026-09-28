# CI 字型安裝步驟：第三方 apt 套件庫 403 不再讓後端品質檢查失敗

**日期**：2026-09-28  
**操作者**：Claude

## 變更內容
- `.github/workflows/quality.yml` 與 `.github/workflows/build-backend.yml` 的「安裝報告圖表所需的 CJK 字型」步驟：
  `apt-get update` 失敗時改為記 `::warning::`，繼續以現有索引執行 `apt-get install fonts-noto-cjk`。兩個 workflow 同步修改。

## 原因
Quality Gate / backend 在 31 秒就失敗，log 顯示 GitHub runner 映像內建的
`https://packages.microsoft.com/ubuntu/24.04/prod noble InRelease` 回 `403 Forbidden`，
`apt-get update` 因而以非零結束，後面的 Ruff、Django check 與測試都沒跑到。
這是 runner 端第三方套件庫的問題，與本次程式變更無關；字型只來自 Ubuntu 官方庫，
不需要 Microsoft 套件庫。

## 影響範圍
- 只影響 CI 的字型安裝步驟；Dockerfile 與正式 image 內容不變。
- 若 Ubuntu 官方庫本身抓不到，`apt-get install` 仍會失敗，不會默默略過（GitHub Actions 以 `bash -e` 執行，`update || echo` 不會中止、install 失敗會中止）。

## 驗證方式
- `uv run python -m unittest tests.test_ci_quality_gate_parity`：4 項通過（apt 行不列入 Quality Gate／build 等價比對）
- 兩個 workflow YAML 以 `yaml.safe_load` 解析成功
- 推送後以 GitHub Actions 實際結果為準
