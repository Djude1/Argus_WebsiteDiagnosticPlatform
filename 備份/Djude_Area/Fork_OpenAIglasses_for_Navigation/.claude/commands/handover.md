---
allowed-tools: Read, Edit, Bash(git:*), Bash(python:*), Bash(cp:*), Bash(ls:*)
description: 交接資料更新檢查 + 缺失語音 log 處理
---

## ⚠️ 交接資料同步規則（每次改動必做，不可省略）

**以下檔案修改後，必須立刻同步一份到 `_交接資料/`：**

| 修改的檔案 | 同步指令 |
|-----------|---------|
| `.env`（模型路徑、API Key、任何設定）| `cp .env _交接資料/.env` |
| `Website/.env` | `cp Website/.env _交接資料/Website.env` |
| `google_Speech_to_Text.json` | `cp google_Speech_to_Text.json _交接資料/` |
| `Google_Api_Key.json` | `cp Google_Api_Key.json _交接資料/` |

並且更新 `_交接資料/README.md` 中對應的說明（尤其是模型路徑、功能開關異動時）。

**`_交接資料/` 是給別人接手時用的，內容過時 = 別人無法正確啟動系統。**

---

## ⚠️ git pull 後必做：從 `_交接資料/` 還原機密檔到專案

`_交接資料/` 不在 git，由人工在各電腦間傳遞。每次 `git pull` 後，執行以下還原：

```bash
# 從交接資料還原機密設定到專案根目錄
cp _交接資料/.env .env
cp _交接資料/Website.env Website/.env
cp _交接資料/google_Speech_to_Text.json .
cp _交接資料/Google_Api_Key.json .
```

若 `_交接資料/` 不存在（新電腦），需先向原作者取得整個 `_交接資料/` 資料夾（加密傳送）。

### 確認還原後的狀態

```bash
python -c "
import os, datetime
pairs = [('.env', '_交接資料/.env'), ('Website/.env', '_交接資料/Website.env')]
for src, dst in pairs:
    src_t = os.path.getmtime(src) if os.path.exists(src) else None
    dst_t = os.path.getmtime(dst) if os.path.exists(dst) else None
    src_s = datetime.datetime.fromtimestamp(src_t).strftime('%Y-%m-%d %H:%M') if src_t else '不存在'
    dst_s = datetime.datetime.fromtimestamp(dst_t).strftime('%Y-%m-%d %H:%M') if dst_t else '不存在'
    in_sync = 'OK' if src_t and dst_t and abs(src_t - dst_t) < 60 else '不同步'
    print(in_sync, src, src_s, '|', dst, dst_s)
"
```

---

## 1. 交接資料同步狀態檢查

```bash
# 比對 .env 最後修改時間（交接資料 vs 主專案）
python -c "
import os, datetime
pairs = [('.env', '_交接資料/.env'), ('Website/.env', '_交接資料/Website.env')]
for src, dst in pairs:
    src_t = os.path.getmtime(src) if os.path.exists(src) else None
    dst_t = os.path.getmtime(dst) if os.path.exists(dst) else None
    src_s = datetime.datetime.fromtimestamp(src_t).strftime('%Y-%m-%d %H:%M') if src_t else '不存在'
    dst_s = datetime.datetime.fromtimestamp(dst_t).strftime('%Y-%m-%d %H:%M') if dst_t else '不存在'
    diff = '⚠️ 需要同步' if src_t and dst_t and src_t > dst_t + 60 else 'OK'
    print(f'{diff}  {src}: {src_s}  |  {dst}: {dst_s}')
"
```

若顯示「⚠️ 需要同步」，立即執行對應的 `cp` 指令。

---

## 2. 缺失語音 log 處理（`voice_missing_log/`）

### 2a. 拉取部署機 push 的 log
```bash
git pull
ls voice_missing_log/
```

### 2b. 查看缺失清單
```bash
python -c "
import os, json
log_dir = 'voice_missing_log'
with open('voice/map.zh-CN.json', encoding='utf-8') as f:
    m = json.load(f)
existing_keys = set(m.keys())

missing = []
for fname in sorted(os.listdir(log_dir)):
    if not fname.endswith('.txt'):
        continue
    with open(os.path.join(log_dir, fname), encoding='utf-8') as f:
        for line in f:
            t = line.strip().rstrip('。！？!?.，,')
            if t and t not in existing_keys:
                missing.append((fname, t))

print(f'共 {len(missing)} 條缺失語音：')
for date, text in missing:
    print(f'  [{date}] {text}')
"
```

### 2c. 新增到 generate_voice.py 並生成 WAV
1. 將缺失文字加入 `generate_voice.py` 的 `PHRASES` 清單
2. 執行生成：`uv run python generate_voice.py`
3. 確認 OK 後刪除已處理的 log 檔

### 2d. 刪除已處理 log
```bash
# 確認生成成功後才刪除
rm voice_missing_log/YYYY-MM-DD.txt
```

### 2e. Commit & Push
```bash
git add voice/map.zh-CN.json voice/ generate_voice.py voice_missing_log/
git commit -m "feat: 預錄缺失語音（來自部署機 log YYYY-MM-DD）"
git push
```

---

## 規則

- **每次對話開始時**：執行步驟 1，確認交接資料有無更新，有則立即告知使用者
- **每次對話開始時**：執行步驟 2a，若有新的 log 檔，執行 2b-2e
- log 只有在對應 WAV 全部成功生成後才能刪除
