# RTK (Rust Token Killer) 使用規則

> RTK 是選用的本機輸出壓縮工具，**不是專案依賴，也不是每台電腦都有安裝**。任何工作流程、測試與 CI 都必須在沒有 RTK 時正常執行。

**核心目的**：壓縮 git/test/build/docker 等命令輸出，節省 60-90% LLM token

## 使用前先偵測

```powershell
Get-Command rtk -ErrorAction SilentlyContinue
```

- 有找到 `rtk`：可依下表選用。
- 沒有找到：直接執行原生命令，不安裝、不報錯、不阻塞任務。
- 安裝位置、版本與套件管理器屬於單機設定，只能記在不提交的本機規則，不得寫進團隊文件。

## 已安裝時的選用方式

當預期輸出超過約 50 行時，可用 RTK 壓縮下列命令輸出：

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

## 不使用 RTK 的情況

1. **RTK 未安裝**：直接使用原生命令。
2. **內建工具更好**：檔案讀寫搜尋優先使用目前執行環境提供的檔案工具，不使用 `rtk ls` / `rtk grep` / `rtk find` / `rtk read` / `rtk tree`。
3. **預期輸出 ≤ 20 行**：RTK 收益不大，維持原命令。
4. **需要完整原始輸出**：維持原命令。
5. **互動式命令**（`git rebase -i` 等）：RTK 不支援互動。

## 命令鏈中的處理

PowerShell 沒有 `&&`，每段都要獨立包：

```powershell
# 錯誤
git add <明確檔案路徑> && git commit -m "msg"

# RTK 已安裝時
rtk git add <明確檔案路徑> ; if ($?) { rtk git commit -m "msg" }

# RTK 未安裝時
git add <明確檔案路徑> ; if ($?) { git commit -m "msg" }
```

本指南不得成為安裝或卸載 RTK 的依據；各機器自行管理選用工具，且不得把單機操作寫回團隊 repo。
