# 複刻產出驗證：非網頁內容不得交付

**日期**：2026-09-07
**操作者**：Claude

## 變更內容

- `backend/apps/rebuild/services.py`：新增 `_looks_like_html()`，三層取回（指定路徑 →
  `/find/file` 搜同名 → ```html 圍欄）每一層都必須通過此檢查才算產出
- `backend/apps/rebuild/tests.py`：新增 `OutputValidationTests`（4 項）
- `docs/opencode-site-rebuild.md`：補上實測到的環境事實與排查順序

## 原因

**真實事故**：使用者下載「優化版」，內容只有一行 `test sudo tee access`。

那是他測試寫入權限時用 `sudo tee` 留在 agent 工作目錄的殘檔，檔名剛好與該次
rebuild 的預期輸出相同。agent 那一輪其實沒寫成功，但 `_extract_optimized_html`
只檢查「內容非空」，就把那 20 bytes 當成優化後的網頁存進 media 並讓使用者下載。

計費也因此出錯：那次被判定為 SUCCEEDED，扣了點數。

## 影響範圍

- 取回的內容必須含 `<html` / `<!doctype html` / `<body` 其一，否則視為未產出
- 前一層失敗不會中斷後續 fallback：殘檔擋在指定路徑時，仍會繼續找 `/find/file`
  與回覆中的圍欄
- 判定為未產出時走既有失敗路徑 → 全額退點

## 這次排查累積的環境事實（已寫進 docs）

追這個問題時連帶釐清了幾件會讓下一個人卡住的事：

1. **agent 只能定義在 `~/.config/opencode/agent/<name>.md`**。放進 `omo.jsonc` 的
   `[opencode].agents` 不會建立新 agent——那只是 omo 對內建 roster 的模型覆寫表。
2. **設定只在啟動時載入**，改完必須 `systemctl restart opencode`。
3. **工作目錄必須屬於 opencode 的執行使用者**。用 `sudo` 在裡面建過檔會讓目錄變成
   `root:root`，症狀是「能編輯既有檔、不能建新檔」，錯誤訊息 `PermissionDenied:
   FileSystem.writeFile` 看起來像 opencode 的權限問題，其實是檔案系統。
   **這次繞了好幾輪才發現——排查順序應該是先 `ls -ld` 再查 permission 設定。**
4. `external_directory` 的 pattern 不匹配目錄本身（`/tmp/opencode/*` ≠ `/tmp/opencode`）。
5. **`.126` 的 `argus` 使用者在 sudo 群組**，代表有 bash 的 `build` agent 可取得 root。
   已記進文件建議移除。

## 驗證方式

- `apps.rebuild` 43 tests OK（新增 4 項，其中一項直接用這次的真實內容當 fixture）
- `ruff check backend` / `manage.py check` 通過
- **對真實 agent 實測**：受限的 `argus-rebuild`（`bash` / `webfetch` / `websearch` /
  `task` 全 deny）在 `chown` 修正後成功寫出檔案，只補了 `<title>` 與 `alt`、
  保留 `<base>` 與原內容

## 待辦

- `external_directory` 限制為了排查被移除，而它並非根因，應加回並實測
- production 端到端尚待使用者按「重新產生」確認
