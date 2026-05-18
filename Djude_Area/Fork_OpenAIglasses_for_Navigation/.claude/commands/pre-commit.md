---
allowed-tools: Read, Bash(git:*), Bash(cp:*), Bash(grep:*), Bash(ls:*)
description: Push 前安全確認 + 交接資料同步
---

## Push 前必做流程（依序執行）

### Step 1：同步機密檔到 `_交接資料/`

```bash
cp .env _交接資料/.env
```

若 `Website/.env` 有異動：
```bash
cp Website/.env _交接資料/Website.env
```

若 `google_Speech_to_Text.json` 或 `Google_Api_Key.json` 有異動：
```bash
cp google_Speech_to_Text.json _交接資料/
cp Google_Api_Key.json _交接資料/
```

> `_交接資料/` 在 `.gitignore`，不會進 git。同步是為了讓另一台電腦 pull 後能從這裡還原機密檔。

---

### Step 2：確認沒有機密檔被 staged

```bash
git diff --cached --name-only
```

以下**絕對不能出現**在 staged 清單：
- `.env`
- `*.json`（服務帳號金鑰）
- `*.pt`、`*.task`（模型檔）
- `_交接資料/`
- `Website/downloads/`、`*.apk`、`mobileclip*.ts`

---

### Step 3：確認沒有 merge conflict 殘留

```bash
grep -rn "<<<<<<\|=======\|>>>>>>" --include="*.py" --include="*.md" . | grep -v ".venv"
```

---

### Step 4：確認 `.claude/commands/` 已包含在 staged 內

SKILL 檔要隨 push 同步到其他電腦：

```bash
git status .claude/commands/
```

若有修改未 staged，執行：
```bash
git add .claude/commands/
```

---

全部確認無誤後執行 commit & push。

---

### Push 完成後：主動告知交接資料狀態

**每次 push 完，必須主動執行以下檢查並告知使用者結果**：

```python
import os, datetime
pairs = [('.env', '_交接資料/.env'), ('Website/.env', '_交接資料/Website.env')]
for src, dst in pairs:
    src_t = os.path.getmtime(src) if os.path.exists(src) else None
    dst_t = os.path.getmtime(dst) if os.path.exists(dst) else None
    src_s = datetime.datetime.fromtimestamp(src_t).strftime('%Y-%m-%d %H:%M') if src_t else '不存在'
    dst_s = datetime.datetime.fromtimestamp(dst_t).strftime('%Y-%m-%d %H:%M') if dst_t else '不存在'
    diff = '⚠️ 需要同步' if src_t and dst_t and src_t > dst_t + 60 else 'OK'
    print(f'{diff}  {src}: {src_s}  |  {dst}: {dst_s}')
```

- **OK**：告知「交接資料同步正常」
- **⚠️ 需要同步**：明確告知使用者「`_交接資料/` 需要手動同步，請執行 `cp .env _交接資料/.env`」

> 規則來源：使用者要求每次 push 後必須主動回報交接資料狀態，不能等使用者問。
