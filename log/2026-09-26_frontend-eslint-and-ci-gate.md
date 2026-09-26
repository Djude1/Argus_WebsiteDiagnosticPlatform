# 前端導入 ESLint，並將 lint／typecheck／test 納入 CI 閘門

**日期**：2026-09-26
**操作者**：Claude

## 變更內容
- 安裝（`frontend/` devDependencies）：`eslint@^9`、`@eslint/js@^9`、`globals`、`typescript-eslint`、`eslint-plugin-react`、`eslint-plugin-react-hooks`。
- 新增 `frontend/eslint.config.js`（flat config）；`package.json` 新增 `lint` 腳本。
- **修正正式站 bug**：`PublicPages.jsx::FreeToolsPage` 使用 `navigate` 卻未宣告——`/free-tools` 單頁檢查結果下方的導流按鈕「登入建立完整掃描」點擊即丟 `ReferenceError`、無反應。來自 `9706623`（2026-09-11，修正產出票06）。
- **移除無效請求**：`SettingsPage` 每次進入都打 `/dashboard/`，結果只用來算一個從未顯示的 `totalFindings`；連同該變數移除。
- 清除既有 lint 發現：未使用的 import（8 個檔案）、未使用的死碼元件 `Sparkline`（`AuthenticatedPages.jsx`，自 2026-07 拆檔後即無人使用）、`catch (e)` 改 `catch {}`。
- `no-irregular-whitespace` 設定略過字串與模板字串（中文文案刻意使用全形空白 U+3000）。
- CI：
  - `.github/workflows/quality.yml` 的 `frontend` job 新增 ESLint、TypeScript 型別檢查、前端測試三步。
  - `.github/workflows/build-frontend.yml` 的「推送 image 前執行前端品質閘門」同步新增三項。
  - `tests/test_ci_quality_gate_parity.py` 新增 `test_frontend_image_build_runs_every_frontend_quality_check`：前端 image build 的檢查不得弱於 Quality Gate 的 `frontend` job（沿用後端既有原則）。
- 同步 `CLAUDE.md`、`AGENTS.md`（常用命令）、`frontend/CLAUDE.md`、`k8s/README.md`。

## 原因
`.jsx` 不經 TypeScript 檢查（`checkJs: false`），引用不存在的名稱時 `vite build` 照樣成功，要到瀏覽器執行才出錯。拆分 `AdminPages.jsx` 時只能靠人工 grep 確認，且導入後立刻在正式站程式碼抓到一例（上述 `/free-tools`）。

ESLint 只在本機跑不構成保護，因此納入 CI；並依 repo 既有原則（image build 會 write-back 上線，閘門不得弱於 Quality Gate），兩邊同時加入並以測試鎖定。

## 影響範圍
- **CI 行為改變（影響所有組員）**：前端 push 若 lint 有 error、型別錯誤或測試失敗，Quality Gate 會紅燈，且**前端 image 不會建出、不會部署**。warning 不擋（目前 1 個：`AdminPages.jsx` drawer 的 `useEffect` 依賴，需另行判斷是否為 bug）。
- CI 時間約增加 30 秒（lint、typecheck、test 各約 10 秒）。
- `/free-tools` 導流按鈕恢復可用；設定頁少一個無用的 API 請求。其餘畫面與行為不變。
- ESLint 固定 9：`eslint-plugin-react` 7.37 的 peer 只到 ESLint 9.7。

## 驗證方式
- `npm run lint`：0 error、1 warning；`npm run typecheck` 0 錯誤；`npm test` 100 passed；`vite build` 成功、CSS 與基準逐位元組相同。
- `uv run python -m unittest discover -s tests`：43 passed（含新增的前端閘門一致性測試）。
- `scripts/verify_repository_text.py`：以暫存 index 模擬「已提交刪除 `useListQuery.js`」後通過（工作區中該刪除尚未 stage，直接執行會因檔案仍被追蹤而失敗）。
- **反證**：
  - 拿掉 `FreeToolsPage` 的 `navigate` 宣告 → `no-undef` 報錯
  - 從 `AdminPages.jsx` 刪掉仍在使用的 `AdminPagination` import → `react/jsx-no-undef` 報錯；同時 `vite build` **0 錯誤照樣成功**（證實這正是 build 攔不住的缺口）
- **需上線後手動確認**：`/free-tools` 執行一次單頁檢查，點「登入建立完整掃描」應導向 `/login`；首次 push 後確認 Quality Gate 的 frontend job 與前端 image build 都綠燈。
