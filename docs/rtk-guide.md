# RTK (Rust Token Killer) 使用規則

**安裝位置**：`C:\Users\ntub\scoop\shims\rtk.exe`（v0.42.0，透過 scoop 安裝，shim 已在 PATH 內，可直接用 `rtk` 呼叫）

**核心目的**：壓縮 git/test/build/docker 等命令輸出，節省 60-90% LLM token

## 呼叫格式

```powershell
rtk <subcommand> <args>
```

## 何時必須使用 rtk

當預期輸出**超過約 50 行**，且屬於下列類型時，**改用 rtk 包裝命令**：

| 原始命令 | 改用 |
|---------|------|
| `git status` / `git diff` / `git log` / `git show` | `rtk git <sub>` |
| `git add` / `git commit` / `git push` / `git pull` | `rtk git <sub>` |
| `gh pr view` / `gh run list` / `gh issue list` | `rtk gh <sub>` |
| `jest` / `vitest` / `playwright test` | `rtk <runner>` |
| `pytest` / `cargo test` / `go test` | `rtk <runner>` |
| `tsc` / `eslint` / `prettier --check` | `rtk tsc` / `rtk lint` / `rtk prettier` |
| `cargo build` / `cargo clippy` / `next build` | `rtk cargo <sub>` / `rtk next build` |
| `docker ps` / `docker logs` / `kubectl get` | `rtk docker <sub>` / `rtk kubectl <sub>` |
| `curl <url>` 大型 JSON | `rtk curl <url>` |
| 觀察大型 log 檔 | `rtk log <file>` |

## 何時**不要**用 rtk

1. **內建工具更好**：檔案讀寫搜尋一律優先用 Claude Code 內建 `Read` / `Grep` / `Glob` / `Edit`，**不要**用 `rtk ls` / `rtk grep` / `rtk find` / `rtk read` / `rtk tree`（這些在 Windows 原生會失敗，因為它們 proxy 到 Unix 命令）。
2. **預期輸出 ≤ 20 行**：rtk 收益不大，維持原命令。
3. **使用者明確要求看完整原始輸出**：維持原命令。
4. **使用者明確說「不要用 rtk」或「直接用原命令」**：立即停止使用，並記住該專案的偏好。
5. **互動式命令**（`git rebase -i` 等）：rtk 不支援互動。

## 命令鏈中的處理

PowerShell 沒有 `&&`，每段都要獨立包：

```powershell
# 錯誤
git add . && git commit -m "msg"

# 正確
rtk git add . ; if ($?) { rtk git commit -m "msg" }
```

## 卸載

`scoop uninstall rtk`（透過 scoop 統一管理，刪除即完整移除；同時移除 `docs/rtk-guide.md` 並清除 CLAUDE.md 中的索引列）。
