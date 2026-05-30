---
name: argus-project
description: Argus 專案專用工作規則。當 Codex 在 D:\GitHub_Project\Argus 工作、使用者提到 Argus、網站健檢 SaaS、SEO/AEO/GEO/security 掃描、Playwright 爬蟲、Django/React/Celery、LLM Agent、API Key/model 選擇、MiniMax/GLM/Gemini、RTK、交接存檔或專案參考資料時，必須使用此 skill；開始實作前必須讀取本 skill 與其 references。
---

# Argus Project

## 核心流程

1. 先讀 `CLAUDE.md`、`Project_說明.md`、`開發計畫.md`，再讀本 skill 的 references。
2. 做任何設計或實作前，先確認需求是否對應使用者目標；若有多種合理解讀，先列出取捨。
3. 嚴禁輸出、記錄或提交 API Key、Token、密碼、私鑰、完整憑證內容或個資。
4. 嚴禁污染全域環境：Python 依賴只能在專案 `.venv` 或 Docker；Node 依賴只能在 `frontend/node_modules`；Playwright browser 必須在專案 `.ms-playwright`。
5. 執行任何 `playwright install` 前，必須在同一命令設定 `PLAYWRIGHT_BROWSERS_PATH=.ms-playwright`。
6. 若工作超過約 20 分鐘，更新 `.sisyphus/argus-handoff.local.md` 做交接存檔。
7. 完成後執行最接近改動面的測試；若找到 `n` 個與本次改動相關的錯誤，補 `n*2` 個不同類型測試。

## 必讀參考

- `references/project-rules.md`：專案定位、硬性規則、20 分鐘交接、測試加倍規則。
- `references/api-provider-workflow.md`：API Key 安全檢查、模型列舉、provider 選擇與 fallback。
- `references/external-references.md`：可參考的 GEO/AEO/crawler/RTK 專案與可取用優點。
- `references/technology-adoption.md`：外部專案技術採納矩陣、MVP/Phase 2 落地任務與不採納項。

## API Provider 原則

- 使用任何 API Key 前，先只驗證授權與可用模型清單；只輸出 provider、HTTP 狀態、模型 ID/能力摘要，不輸出金鑰或原始錯誤 body。
- 專案需要 LLM Agent/tool calling 時，優先使用已通過 tool-calling 測試且最適合任務的 provider。
- 若 GLM API 出錯、受限或回 429，改用 Gemini 或 MiniMax；目前已知專案中有 MiniMax 設定，但每次使用前仍需重新測試。

## RTK 原則

- 大型 git/test/build/docker/log 輸出預期超過約 50 行時，優先用 `D:\RTK\bin\rtk.exe` 包裝。
- 小輸出、檔案搜尋、檔案讀寫、互動式命令、使用者要求原始輸出時，不使用 RTK。

## 環境隔離原則

- 不使用 `pip install`、`npm -g`、全域 PATH 修改或使用者層級瀏覽器安裝。
- Python：只使用 `uv sync`、`uv run`，讓依賴留在專案 `.venv`。
- Frontend：只在 `frontend/` 執行 `npm.cmd install`，讓依賴留在 `frontend/node_modules`。
- Playwright：用 `$env:PLAYWRIGHT_BROWSERS_PATH=".ms-playwright"; uv run playwright install chromium`，讓瀏覽器留在專案 `.ms-playwright`。
- 若發現工具預設寫到全域位置，必須立即停止、修正設定、記錄地雷並告知使用者。

## 交接存檔

每次交接只記錄可公開的工程狀態：

- 目前目標與成功條件
- 已讀文件與主要決策
- 已改檔案與未完成項目
- 測試結果、錯誤數與新增測試要求
- API provider 狀態摘要，不含任何秘密值
- 下一步建議
