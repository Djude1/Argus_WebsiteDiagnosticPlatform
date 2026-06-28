# 2026-06-19 合併 origin/main（Email/UI/exposure-secret ←→ 本機 SRI/DNS/Kali）

## 變更內容

本機 `main` 與 `origin/main` 分岔（本機領先 11、落後 5），執行 `git merge origin/main` 整合兩條平行功能線：

- **origin（落後的 5 個 commit）**：忘記密碼流程、購點收據 Email（Resend SMTP）、dashboard/CMS/admin UI 改善、`exposure_scanner`（敏感檔案外洩）+ `secret_scanner`（硬編碼秘鑰偵測）。
- **本機（領先的 11 個 commit）**：`sri_scanner`（SRI 缺失）、`dns_scanner`（SPF/DMARC/DNSSEC）、`kali_tools` 主動驗證攻擊鏈接進掃描流程。

## 衝突解決（3 檔，全為 union 型「兩邊各加各的」）

| 檔案 | 解法 |
|---|---|
| `backend/apps/scans/security/owasp_mapper.py` | `_RULE_OWASP_MAP` 兩邊新增的 rule_id 全保留（sri/dns/kali + exposure/secret） |
| `backend/apps/scans/tasks.py` | import 區三個 import 全保留並依字母序排；body 兩段（Kali 驗證 + SRI/DNS、secret 偵測 + robots/exposure）由 git 自動合併，位置不衝突 |
| `backend/apps/scans/security/CLAUDE.md` | scanner 表格與設計原則章節兩邊新增全保留；`kali_tools` 一列取本機「已建」版（origin 仍寫「待建」，與事實不符） |

`backend/config/settings.py` 由 git 乾淨自動合併（本機 Kali 設定 + origin Email 設定位置不同，無衝突）。

## 影響範圍

- 後端掃描流程：合併後同時具備 origin 的 exposure/secret 被動偵測與本機的 SRI/DNS/Kali。
- migration：origin 新增 `accounts/0003_passwordresettoken`，本機未動 accounts migration，編號不撞。
- 前端 `App.jsx` / `styles.css`、Email/CMS/admin 功能皆由 origin 帶入（純加法，未與本機衝突）。

## 驗證方式

- `git diff --check`：exit 0，無空白/標記殘留；全域 grep 確認無 `<<<<<<<` / `=======` / `>>>>>>>` 殘留。
- `uv run ruff check`（合併到的檔案）：All checks passed。
- `uv run python manage.py check`：0 issues。
- `uv run python manage.py makemigrations --check --dry-run`：No changes detected。
- `uv run python manage.py test apps`：**367 tests，OK（78.9s）**。
- 確認 `tasks.py` 被 import 的 9 個 security 模組檔案皆存在、兩條功能線呼叫點皆在。

## 待辦

- 尚未 push（依 git-safety 規範等使用者明確同意）。push 前建議在 Docker 環境（`localhost:8080`）做掃描 E2E，確認 SRI/DNS/Kali 與 exposure/secret 同時掛上後實跑無誤。
