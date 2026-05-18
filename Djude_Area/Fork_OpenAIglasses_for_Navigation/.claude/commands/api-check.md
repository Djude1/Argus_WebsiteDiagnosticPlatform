---
allowed-tools: Bash(uv run python*), Read
description: 測試所有 AI API 金鑰是否有效（Gemini Flash/TTS、WaveNet TTS、DashScope、Vertex AI、Google 憑證）
---

執行以下腳本，確認所有 AI API 金鑰與憑證皆可正常呼叫。**每次 pull 後、每次 AI 相關模組修改後必做。**

```python
# uv run python -c "exec(open('.claude/commands/api-check.py').read())"
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

results = {}
failed = []

# 1. Gemini Flash（AI Studio LLM）
try:
    from omni_client import _call_flash
    r = _call_flash([{'text': '1+1=?'}], '')
    results['Gemini Flash'] = f"[OK] {repr(r[:20])}" if r else "[FAIL] empty response"
    if not r: failed.append('Gemini Flash')
except Exception as e:
    results['Gemini Flash'] = f"[FAIL] {type(e).__name__}: {str(e)[:100]}"
    failed.append('Gemini Flash')

# 2. Gemini TTS（AI Studio TTS）
try:
    from omni_client import _call_tts
    pcm = _call_tts('前方有斑馬線，請注意。', 'Aoede')
    results['Gemini TTS'] = f"[OK] {len(pcm)} bytes" if pcm else "[FAIL] empty audio"
    if not pcm: failed.append('Gemini TTS')
except Exception as e:
    results['Gemini TTS'] = f"[FAIL] {type(e).__name__}: {str(e)[:100]}"
    failed.append('Gemini TTS')

# 3. WaveNet TTS（Google Cloud TTS，需服務帳號憑證）
try:
    from audio_player import _wavenet_tts
    pcm = _wavenet_tts('前方有斑馬線，請注意。')
    results['WaveNet TTS'] = f"[OK] {len(pcm)} bytes" if pcm else "[FAIL] empty audio (check credentials)"
    if not pcm: failed.append('WaveNet TTS')
except Exception as e:
    results['WaveNet TTS'] = f"[FAIL] {type(e).__name__}: {str(e)[:100]}"
    failed.append('WaveNet TTS')

# 4. Vertex AI 設定（GCP_PROJECT_ID 未設定時自動走 AI Studio，不算失敗）
try:
    from config import USE_VERTEX_AI, GCP_PROJECT_ID, GCP_LOCATION
    if GCP_PROJECT_ID:
        from omni_client import _get_vertex_client
        client = _get_vertex_client()
        results['Vertex AI'] = "[OK] client initialized" if client else "[FAIL] init failed"
        if not client: failed.append('Vertex AI')
    else:
        results['Vertex AI'] = "[WARN] GCP_PROJECT_ID not set → fallback to AI Studio (OK)"
except Exception as e:
    results['Vertex AI'] = f"[FAIL] {type(e).__name__}: {str(e)[:100]}"
    failed.append('Vertex AI')

# 5. DashScope ASR
try:
    import dashscope
    key = os.getenv('DASHSCOPE_API_KEY', '')
    if key:
        results['DashScope ASR'] = f"[OK] key set ({key[:8]}...)"
    else:
        results['DashScope ASR'] = "[FAIL] DASHSCOPE_API_KEY not set"
        failed.append('DashScope ASR')
except Exception as e:
    results['DashScope ASR'] = f"[FAIL] {type(e).__name__}: {str(e)[:100]}"
    failed.append('DashScope ASR')

# 6. Google 服務帳號憑證檔案
try:
    from config import GOOGLE_CREDENTIALS_PATH
    if os.path.exists(GOOGLE_CREDENTIALS_PATH):
        results['Google Credentials'] = f"[OK] {GOOGLE_CREDENTIALS_PATH}"
    else:
        results['Google Credentials'] = f"[FAIL] not found: {GOOGLE_CREDENTIALS_PATH} → WaveNet/STT will fail"
        failed.append('Google Credentials')
except Exception as e:
    results['Google Credentials'] = f"[FAIL] {type(e).__name__}: {str(e)[:100]}"
    failed.append('Google Credentials')

# 輸出結果
print("\n=== AI API Check ===")
for k, v in results.items():
    print(f"  {k}: {v}")

if failed:
    print(f"\n[!] 以下 API 失效，請修復後再繼續: {', '.join(failed)}")
    sys.exit(1)
else:
    print("\n[ALL PASS] 所有 AI API 正常")
```

## 執行方式

```bash
uv run python -c "
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
exec(open('.claude/commands/_api_check_impl.py').read())
"
```

或直接在 Claude Code 下 `/api-check` 叫出此 skill，Claude 會自動執行上方腳本並回報結果。

## 判讀規則

| 狀態 | 意義 |
|------|------|
| `[OK]` | API 有效，有實際回傳資料 |
| `[WARN]` | 非錯誤，功能降級但可運作（如 Vertex AI 無 GCP_PROJECT_ID） |
| `[FAIL]` | API 失效，**必須修復**，否則功能中斷 |

## 常見修復方式

- **Gemini Flash/TTS 失敗**：檢查 `.env` 的 `GEMINI_API_KEY` 是否有效，可能配額耗盡
- **WaveNet TTS 失敗**：`google_Speech_to_Text.json` 不存在或服務帳號無 TTS 權限
- **DashScope ASR 失敗**：`.env` 缺少 `DASHSCOPE_API_KEY`
- **Google Credentials 失敗**：從 GCP Console 下載服務帳號 JSON 放到專案根目錄
