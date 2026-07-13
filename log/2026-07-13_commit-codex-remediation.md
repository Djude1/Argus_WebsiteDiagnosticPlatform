# 把 codex 全專案稽核修復成果固化進 main

**日期**：2026-07-13
**操作者**：Sisyphus（GLM-5.2 via OpenCode）

## 變更內容

把 codex 在 `codex/full-audit-remediation` 分支 working tree 累積的大量未 commit 成果（21 項稽核修復 + K8s NetworkPolicy + 前端 React domain 重構 + CI quality gate + 文件同步），切到 `main` 分支後分 5 個邏輯群組 commit 進版控。

### 5 個 commit（順序 = 提交順序）

| # | hash | 主題 | 檔案數 | 變動量 |
|---|------|------|--------|--------|
| 1 | `b0616aa` | feat(k8s): 強化 K8s 部署資安邊界與正式 WSGI 設定 | 12 | +538 / -25 |
| 2 | `9af4032` | fix(backend): 21 項稽核修復 — SSRF / JWT / 金流 / 密碼重設 / 取消競態 | 39 | +2009 / -271 |
| 3 | `241972d` | refactor(frontend): App.jsx 8000 行拆解為 React domain features | 22 | +8373 / -7763 |
| 4 | `52671e3` | ci/deps: 正式 Gunicorn 基線 + 4-job CI quality gate | 9 | +365 / -29 |
| 5 | `64581ca` | docs: 同步稽核修復文件 + 新增 AGENTS.md / skills / memory | 20 | +1013 / -108 |

合計：102 個檔案、+12298 / -8196。

## 原因

Codex 完成修復後只把 log 寫進 `log/2026-07-13_full-audit-remediation.md`，所有實際變動都留在 working tree 未 commit，HEAD 仍等於 `origin/main`。任何 `git checkout` / `git reset` 都會讓這些成果消失，組員 pull 也看不到。為避免成果丟失並讓 CI/CD 與組員接手，必須立即固化進版控。

## 影響範圍

- **K8s 部署**：07-network-policies.yaml（7 個 NetworkPolicy）+ 04-backend Gunicorn 改造 + 應用層配套（client_ip / egress / proxy_headers / throttling）。
- **後端應用**：JWT cookie + CSRF 原子輪替、password reset HMAC digest、綠界 ecpay_test 冪等入點、掃描取消競態修復、reviews N+1 修正。
- **前端**：App.jsx 從 8000 行拆到 164 行 + React.lazy route-level + features/components/shared 三層。
- **CI**：quality.yml 4 個 job（含 Kustomize render 驗證 7 個 NetworkPolicy）。
- **文件**：AGENTS.md、3 個 skill、MEMORY.md、memory/、README/ONBOARDING/CLAUDE.md 全面同步。
- **部署機**：**尚未 push**，所以 `https://xn--gst.tw/` 暫時不受影響；push 後若部署機有 auto-pull，會抓到新版（含 Gunicorn + NetworkPolicy）。

## 驗證方式

- **commit 前**：
  - `uv run ruff check backend` → All checks passed
  - `uv run python backend/manage.py check` → 0 issues
  - `uv run python backend/manage.py makemigrations --check --dry-run` → No changes detected
  - `kubectl kustomize k8s` → render 出 7 個 NetworkPolicy（符合 README 預期）
  - 全檔掃敏感字串（API key / password / token / private key）→ 0 match
  - 逐 commit `git diff --staged` 驗證檔案清單與 stat
- **commit message 編碼**：用 Python `subprocess.run(['git', 'cat-file', 'commit', 'HEAD'])` 直接讀 raw bytes，確認繁體中文以 UTF-8 正確儲存（`E5 BC B7 E5 8C 96` = 強化）。PowerShell console 顯示亂碼是 codepage 問題，git 儲存的 bytes 正確。
- **commit 後**：
  - `git log --oneline -6` → 5 個新 commit + bd7ecfd
  - `git status --short` → 完全空白（working tree 乾淨）
  - `git rev-list --count origin/main..HEAD` → 5

## 待辦（未執行）

- **未 push**：按 `argus-git-safety` skill 規範，push 需使用者明確同意。
- **未在實機驗證 NetworkPolicy 封包矩陣**：參見 `k8s/README.md` 第 82-122 行的驗證腳本，需要在實際 PVE 叢集跑。
- **TRUSTED_PROXY_CIDRS 預設 `10.0.0.0/8`** 需依實際 Pod CIDR 調整。
- **NGF 上傳大小 ClientSettingsPolicy**（待辦 1）、**TLS / 網域**（待辦 5）尚未實作。
