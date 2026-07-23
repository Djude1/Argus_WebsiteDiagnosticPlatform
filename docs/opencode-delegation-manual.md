# opencode CLI Subagent 委派說明書（Claude Code ＋ Codex 通用）

> **專案觸發條件**：當使用者明確強調「使用 OpenCode 作為 subagent」時，該任務必須先讀本手冊並套用完整委派、監工與驗收流程；未明確觸發時不自動擴張委派範圍。

> 給 AI harness agent（Claude Code 或 Codex）看的操作手冊：如何把「程式實作」委派給
> 本機 opencode CLI（已裝 oh-my-openagent 多代理編排層）、如何監工、如何判斷完成。
> 本手冊可攜——複製到任何專案的 `docs/`，並在 CLAUDE.md 與 AGENTS.md 各加一行指針（見 §9）。
>
> 最後校準：2026-07-15，opencode 1.17.18，oh-my-openagent@latest（關鍵字/旗標皆對照安裝版實測，非猜測）。

---

## 0. 角色分工（一句話版）

**你（Claude Code / Codex）＝建築師＋監工＋驗收員；opencode＝施工隊。**
規格你寫、進度你盯、完成與否你親自驗證——絕不因為 opencode 說「done」就信。

## 1. 本機環境事實（已驗證，照用勿重查）

- 執行檔：`opencode`（PATH 內），版本 1.17.18。
- 全域設定：`~/.config/opencode/opencode.jsonc`（插件清單）＋ `~/.config/opencode/oh-my-openagent.jsonc`（agent→模型路由）。
- 全域 rules（每個 opencode session 自動載入）：`rules/image-delegation.md`、`rules/vision-autonomy.md`
  ——opencode 主模型**無視覺**，已被規則強制把看圖委派給它自己的視覺 subagent。
- 專案級可加自訂 agent：`<專案>/.opencode/agents/*.md`（frontmatter 定 model/permission，範例見挖礦專案的 `vision-debugger.md`）。

### agent 陣容（oh-my-openagent）

| Agent | 模型（本機設定） | 角色 | 你何時指名它 |
|---|---|---|---|
| **sisyphus** | GLM-5.2（fallback 5.1/4.7） | 主 orchestrator，預設 agent；規劃＋委派＋硬推到完成 | 預設就是它，一般不用 `--agent` |
| explore | MiniMax-M3 | 快速 codebase grep | 只要查不改時 |
| librarian | MiniMax-M3 | 外部文件/OSS 原始碼查證 | 查 SDK/庫用法 |
| oracle | GLM-5.2 | 唯讀高智商顧問（架構/難 bug） | 要第二意見不要動手時 |
| prometheus | GLM-5.2 | 訪談式規劃（產計畫不寫 code） | 大型任務先出計畫 |
| atlas | GLM-5.2 | 照 prometheus 計畫執行 | `--command start-work` |
| metis / momus | GLM-5.2 | 計畫的漏洞分析／嚴格審查 | 由規劃鏈自動叫，不用手動 |
| multimodal-looker | MiniMax-M3（**有視覺**） | 看圖/截圖/PDF | opencode 內部自委派用；你自己有視覺就別繞這條 |
| sisyphus-junior | MiniMax-M3 | category 派生的執行工 | 由 sisyphus 自動叫 |
| hephaestus | （本機停用） | GPT 系深度自主工 | 不可用，別指名 |

**要點**：這些 subagent 是 opencode「內部」的分工。你委派時 99% 情況只需把任務交給預設
agent（sisyphus），它自己會往下派。你唯一常用的指名是 `--agent plan` / `--agent build`
（opencode 原生兩態）或完全不指名。

### 魔法關鍵字（安裝版 regex 實測）

寫在 prompt 訊息裡（**不能在 code block/inline code 內**、訊息不能以 `/` 開頭）即觸發：

| 關鍵字 | Regex | 效果 |
|---|---|---|
| `ultrawork` 或 `ulw` | `\b(ultrawork\|ulw)\b`（不分大小寫） | 全自動模式：自己探索、研究、實作、驗證、不完成不停 |
| `hyperplan` 或 `hpp` | `\bhyperplan\b`／`hpp` | 多重敵意 critic 規劃 |
| `team mode` | `\bteam[\s_-]?mode\b` | 多成員平行團隊（重、耗 token，慎用） |

### headless 可用的內建指令（`--command`，名稱不帶斜線）

`start-work`（叫 atlas 執行最新計畫）、`ulw-loop`（多目標自迴圈）、`handoff`、
`refactor`、`remove-ai-slops`、`stop-continuation`、`hyperplan`。

## 2. 什麼時候委派（硬規則）

**一律委派 opencode**：新功能、bug 修、重構、跨檔改動——「程式實作」全部。
不因「改動小」自己動手（這條被違反過多次，是慣例不是建議）。

**例外（你自己直接做）**：
1. 資產/文件/memory 檔案
2. 一行 config 調參
3. opencode 跑完後對**同一批檔案**的小幅收尾補丁（併發改同檔會衝突，等它結束再補）
4. opencode 確認空轉/故障後的 fallback inline 實作（見 §6）

## 3. 委派前：你先做完「模型做不到的事」

opencode 主模型是純文字模型。凡是需要**視覺**或**實測**的事實，你先做完、寫死進規格：

- 截圖量測座標/顏色/區域；裁測試 fixtures
- 用真實引擎實測偵測配方（哪個 OCR/前處理可靠是「測出來的」不是猜的）
- 抓環境陷阱（DPI、視窗座標系差異、路徑編碼……）
- 讀清楚要模仿的現有樣板檔案，把檔名列進規格

## 4. 規格書怎麼寫（成敗關鍵）

存成獨立檔案（建議 `<專案>/.omc/specs/` 或 scratchpad），內容 checklist：

```markdown
# 任務：<一句話>

## 先讀這些檔案（照此順序）
- path/to/樣板.py          ← 要模仿的既有實作
- path/to/config.py        ← 參數集中地，格式照抄
- tests/test_樣板.py       ← 測試寫法樣板

## 已驗證事實（照用，勿重新推導、勿嘗試自行驗證）
- <座標/門檻/OCR 配方/量測數據，含出處：「實測 2026-XX-XX」>

## 實作規格
- <行為、邊界、安全取向（如「寧漏勿誤」方向）>

## 限制
- 不要嘗試讀取任何圖片檔（.png/.jpg）——視覺事實已全部寫在上面
- 不要 git commit（留人工審查）
- TDD：先寫失敗測試再實作

## 完成標準
1. `<測試指令，如 python -m pytest -q>` 全綠
2. 最後一步：建立 `.omc/delegate/DONE-<任務名>.md`，內容＝改了哪些檔＋測試輸出摘要
```

**DONE 哨兵檔是給你的完成訊號**（見 §6），但**不是**驗收依據——驗收永遠自己重跑。

## 5. 怎麼下指令（雙 harness 食譜）

### 共通核心命令

```bash
cd "<專案根>" && opencode run "$(cat .omc/specs/spec_任務名.md)" --title 任務名
```

- 大/模糊任務想要它「不完成不停」：把規格第一行寫成 `ultrawork`（頂層純文字，勿放 code block）。
- 照計畫執行既有 plan：`opencode run --command start-work`。
- 指定模型（跳過路由）：`-m zai-coding-plan/glm-5.2`；調 reasoning：`--variant high`。
- 排錯時多開：`--print-logs --log-level INFO`。
- **`--auto` 是最後手段**（自動核可所有未明示拒絕的權限，危險）：只有觀察到 run 卡在
  permission 等待時才用。歷史成功案例皆未用 `--auto`。

### Claude Code 版（有原生背景執行）

用 Bash 工具（Git Bash 語法、`run_in_background: true`——前景 10 分鐘上限裝不下動輒
20 分鐘以上的 run）：

```bash
cd "/c/Users/puppy/.../<專案>" && \
  opencode run "$(cat .omc/specs/spec_任務名.md)" --title 任務名 2>&1 | tail -40
```

背景任務結束時 harness 會通知你；中途進度**不要看輸出**（stdout buffer 到結束才吐，
中途空白＝正常），用 `git status --short` 看它動了哪些檔。

### Codex 版（無原生背景參數→detached＋log＋輪詢）

```bash
cd "/c/Users/puppy/.../<專案>" && mkdir -p .omc/delegate && \
  nohup opencode run "$(cat .omc/specs/spec_任務名.md)" --title 任務名 \
    > .omc/delegate/run-任務名.log 2>&1 & echo $! > .omc/delegate/run-任務名.pid
```

之後每隔幾分鐘用**新的**shell 呼叫輪詢（見 §6 的三行檢查）。PowerShell 環境可改用：
`Start-Process bash -ArgumentList '-lc','cd /c/... && opencode run ... > log 2>&1' -WindowStyle Hidden`。

### 重複多次委派（同一工作日多任務）

每次 `opencode run` 都要冷啟動插件＋MCP（數秒～數十秒）。先開常駐伺服器可免去：

```bash
opencode serve --port 4096          # 開一次，放著（背景/獨立視窗）
opencode run --attach http://localhost:4096 "$(cat spec.md)" --title 任務名
```

### 平行委派多工（謹慎）

- **Preflight**：發任務前先 `opencode --version`（1 秒內回＝執行檔健在，壞掉早知道）。
- 兩個 run **絕不可改同一批檔案**（改動衝突無仲裁）；分屬不同模組/目錄才平行。
- **啟動間隔錯開 5–10 秒**：同時冷啟動會搶同一份 session storage/cache（此建議源自
  社群 opencode-cli skill 的 cache race 觀察）；用 `serve`＋`--attach` 時同理。
- 網路/供應商偶發失敗屬常態：一次失敗先重試（見 §6 協議），不要立刻歸因於規格。

### 續 session（驗收不過請它修）

```bash
opencode run -c "pytest 有 2 個紅燈：<貼失敗輸出>。修到全綠，其餘不動。"
# 或指定舊 session：opencode session list 找 id → opencode run -s <id> "..."
# 想留原狀分岔實驗：加 --fork
```

## 6. 監工：進度判讀與空轉偵測

**鐵則：輸出檔中途空白＝正常（buffer 到結束才吐），絕不能拿它判斷「沒在跑」。**
進度的真訊號是「檔案有沒有動」：

```bash
git -C "<專案根>" status --short            # 它動了哪些檔（最可靠）
ls .omc/delegate/DONE-任務名.md 2>/dev/null  # 哨兵檔出現＝它自認完成
ps -W | grep -i opencode                     # 行程還活著嗎（Git Bash；PS 用 tasklist | findstr /i opencode）
```

### 空轉（stall）判定與處置——本機踩過的真實故障

已知故障模式（2026-07-10 實錄）：headless run 在 init 之後**卡死零動作**——log 停在
`bootstrapping → loading config → init → cleanup`，之後零 LLM 呼叫、零檔案改動，只剩
心跳空轉；兩次各燒 1hr／22min 全空。疑因中文路徑編碼／插件載入（同機 2026-07-11 又
整批成功過，故障非必然、無法事前預測）。

**處置協議**：
1. 委派後 **~3 分鐘**內查一次 `git status --short`：若零檔案改動且 opencode CPU 只有微
   弱心跳→判空轉，**直接殺掉**（`kill $(cat run-*.pid)` 或 taskkill），不要再等。
2. 空轉一次→可重試一次（先加 `--print-logs --log-level INFO` 收證據）。
3. 重試又空轉→**放棄委派，你自己 inline 實作**（規格書已寫好＝實作藍圖現成，inline
   反而快而確定）。事後在專案筆記記一筆。
4. log 出現 `failed to load plugin ...` 多為**非致命**（照樣能跑）；真的懷疑插件壞→
   `--pure` 裸跑驗證（但會失去 oh-my-openagent，僅作隔離診斷用）。

## 7. 驗收協議（exit 0 ≠ 成功）

opencode 行程結束（背景通知/輪詢到行程消失）後，**依序**做：

1. **看收尾輸出**：log 尾段（`tail -60 run-*.log`）＋ DONE 哨兵檔內容——只當「它的自我
   報告」讀，不當證據。
2. **親自重跑測試**：`python -m pytest -q`（或該專案的測試指令）。紅燈→回 §5 續 session 修。
3. **親自審 diff**：`git diff` 逐檔看——重點：是否越界改了規格外的檔、註解風格是否照抄
   專案、有沒有偷 commit（規格禁止）、有沒有把「已驗證事實」擅自改掉。
4. **紅燈驗證（可行時）**：把核心修復暫時 revert、確認新測試會轉紅、再還原——證明測試
   真的鎖住了行為。
5. **端到端驗證（有 runtime 面時）**：實際跑受影響的流程，不只靠測試。
6. 全過→**由你 commit**（訊息含 Co-Authored-By 慣例照專案規則）。任何一步不過→修法
   二選一：小補丁自己動手（§2 例外 3）、或 `opencode run -c` 讓它修。

**判斷樹（速查）**：

```
行程結束?
├─ 否，>3min 且 git status 零改動 → 空轉協議（§6）
└─ 是
   ├─ exit ≠ 0 → 讀 log 尾段找錯 → 重試(加 log 旗標) 或 inline
   └─ exit 0 → 重跑測試
      ├─ 紅 → opencode run -c "修 <失敗輸出>" （上限 2 輪，再敗轉 inline）
      └─ 綠 → 審 diff → 紅燈驗證 → e2e → 你 commit
```

## 8. 疑難排解速查

| 症狀 | 對策 |
|---|---|
| 輸出檔一直空白 | 正常（buffer），看 `git status --short` |
| init 後全無動作 | §6 空轉協議，別等超過 3 分鐘 |
| 權限卡住不動 | 確認後才用 `--auto`（危險）；或專案 `.opencode/opencode.json` 設 permission |
| 插件載入錯誤 | 多為非致命；隔離診斷用 `--pure` |
| 想看它在想什麼 | `--print-logs --log-level INFO`（stderr 即時出，不受 stdout buffer 影響） |
| 找 session 續命 | `opencode session list` → `-s <id>`；`-c`＝最近一個 |
| 用量統計 | `opencode stats` |
| 機器可解析輸出 | `--format json`（raw JSON events 流） |

## 9. 安裝到目標專案（一次性設定）

1. 複製本檔到 `<專案>/docs/opencode-delegation-manual.md`。
2. `CLAUDE.md`（Claude Code 讀）加：

   ```markdown
   ## 程式實作委派
   程式實作（新功能/bug修/重構/跨檔改動）一律委派本機 opencode CLI，
   流程、監工與驗收協議照 `docs/opencode-delegation-manual.md` 執行；
   例外與空轉 fallback 也在該文件。
   ```

3. `AGENTS.md`（Codex 讀）加**同一段**（Codex 用 §5 的 detached＋輪詢食譜）。
4. 建 `mkdir -p .omc/specs .omc/delegate`，並把 `.omc/delegate/` 加進 `.gitignore`。
5. （可選）若專案需要 opencode 內部視覺 subagent：仿挖礦專案
   `.opencode/agents/vision-debugger.md` 建專案版，嵌入該專案的領域知識。
