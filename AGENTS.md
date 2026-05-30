# Argus Agent Instructions

## 必讀順序

所有在本專案工作的 agent，開始任何設計、實作、測試、API 驗證或文件更新前，必須依序讀取：

1. `CLAUDE.md`
2. `Project_說明.md`
3. `開發計畫.md`
4. `skills/argus-project/SKILL.md`
5. `skills/argus-project/references/project-rules.md`
6. `skills/argus-project/references/api-provider-workflow.md`
7. `skills/argus-project/references/external-references.md`
8. `skills/argus-project/references/technology-adoption.md`
9. `.sisyphus/argus-project-memory.md`

## 專案硬性規則

- 所有回覆與文件使用繁體中文。
- 不得輸出、記錄、提交 API Key、Token、密碼、私鑰、完整憑證 JSON 或個資。
- 禁止污染全域環境：Python 套件只能透過 `uv` 進入專案 `.venv` 或 Docker；Node 套件只能安裝在 `frontend/node_modules`；Playwright 瀏覽器必須使用專案內 `.ms-playwright`。
- 執行任何 `playwright install` 前，必須在同一命令設定 `PLAYWRIGHT_BROWSERS_PATH=.ms-playwright`，不得寫入使用者層級 `AppData/Local/ms-playwright`。
- 做之前先確認是否符合使用者真正需求；不要只完成表面文字。
- 工作超過約 20 分鐘，更新 `.sisyphus/argus-handoff.local.md`。
- 完成後執行最接近改動面的測試；若找到 `n` 個與本次改動相關錯誤，新增至少 `n*2` 個不同類型測試。
- Argus 固定技術棧為 React 18/Vite/Tailwind/Zustand、Django 5/DRF、Celery/Redis、Playwright Python async、SQLite dev/PostgreSQL prod、python-docx、Docker Compose；不要建議替換技術棧。
- 法律授權、same-origin、深度/頁數限制、`robots.txt`、被動資安預設、Active 額外授權與 RPS 限制不可省略。

## API Provider 規則

- 使用任何 API Key 前，先安全測試該 key 可用模型與能力；只輸出 provider、模型名稱、HTTP 狀態與能力摘要。
- Phase 2 Agent 主力優先 `MiniMax-M2.7`；GLM 可用 `glm-4.7-flash` / `glm-4.5-flash` 作第二順位；Gemini 作分析與備援。
- 若 GLM 回 429、授權失敗、配額不足、模型不可用或 tool calling 失敗，改用 Gemini 或 MiniMax。

## 參考資料

使用者提供的外部參考與 GEO checklist 已整理在 `skills/argus-project/references/external-references.md`，可採納技術與不採納項整理在 `skills/argus-project/references/technology-adoption.md`。需要做 GEO/AEO/爬蟲/報告 UX/RTK 相關功能時，先讀這兩個檔案。
