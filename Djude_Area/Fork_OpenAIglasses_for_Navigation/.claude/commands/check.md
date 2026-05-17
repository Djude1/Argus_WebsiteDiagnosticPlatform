---
allowed-tools: Read, Grep, Bash(python:*), Bash(grep:*)
description: AI 眼鏡專案修改驗證（含 TTS、Vertex AI 專屬測試）
---

在通用 /check 之上，額外執行以下專案特有驗證。

## TTS 改動後必做

```python
# 直接打 API，確認回傳 bytes > 0
import omni_client as oc
pcm = oc._call_tts('前方有斑馬線，請注意。', 'Aoede')
assert pcm and len(pcm) > 0, "Gemini TTS 失敗"

from audio_player import _wavenet_tts
pcm = _wavenet_tts('前方有斑馬線，請注意。')
assert pcm and len(pcm) > 0, "WaveNet TTS 失敗"
```

**TTS 地雷**：
- Gemini TTS 對 ≤4 字短句/問句 → 400（模型限制，非 bug）
- Gemini TTS 不支援 `systemInstruction` → 500
- 短句播報必須走 WaveNet，不能走 Gemini TTS

## Vertex AI 改動後必做

```python
import omni_client as oc
oc._VERTEX_EXHAUSTED = False

# 1. Vertex 正常呼叫
result = oc._call_flash([{'text': '1+1=？只回數字'}], '')
assert result

# 2. 自動切換
oc._mark_vertex_exhausted()
assert not oc._use_vertex()
result = oc._call_flash([{'text': '1+1=？只回數字'}], '')
assert result

# 3. 串流
oc._VERTEX_EXHAUSTED = False
chunks = list(oc._stream_flash_sync([{'text': '說一個顏色'}], ''))
assert chunks
```

## config.py / .env 改動後必做

```bash
.venv/Scripts/python -c "import config; print('OK')"
```

## model_server.py 改動後必做

```python
import asyncio, model_server as ms

ms._models = {'yolo-seg': object(), 'yolo-obs': object(), 'trafficlight': object()}

async def test():
    ms._init_locks()
    locks = ms._inference_locks

    # 1. 每個模型各自有鎖
    for name in ms._models:
        assert name in locks, f'{name} 鎖不存在'

    # 2. 不同模型鎖互相獨立
    assert locks['yolo-seg'] is not locks['yolo-obs'], '鎖不獨立'

    # 3. Skip-if-busy：yolo-seg 忙時 yolo-obs 仍可取得
    async with locks['yolo-seg']:
        assert locks['yolo-seg'].locked()
        assert not locks['yolo-obs'].locked()
        async with locks['yolo-obs']:
            pass  # 可以取得

    print('model_server 測試通過')

asyncio.run(test())
```

## Google 服務優先級（必遵守）

**Google Cloud 試用金永遠優先，API Key 永遠備用。**

所有 Google 相關服務都遵循同一模式：
1. **主力**：Google Cloud（服務帳號憑證，消耗試用金）
2. **備用**：Gemini AI Studio（免費 API Key 輪換）
3. 只有試用金耗盡或 GCP 請求失敗時，才降級到 API Key

適用範圍：
- TTS：Google Cloud WaveNet 優先 → Gemini TTS 備用
- LLM：Vertex AI 優先 → AI Studio 16-Key 輪換備用
- ASR：Google Cloud Speech-to-Text（目前無備用）

**禁止**：因為 API Key「免費」就優先使用，試用金才是主力。

## YOLO 障礙物偵測模型地雷（必遵守）

### 白名單必須覆蓋模型全部類別

`obstacle_detector_client.py` 和 `model_server.py` 的 `OBSTACLE_WHITELIST` 必須包含
目前 `OBSTACLE_MODEL` 的**所有**類別，否則不在白名單內的類別會被靜默過濾掉。

**換模型前必做驗證**：

```python
from ultralytics import YOLO

# 換成實際使用的模型路徑
m = YOLO('model/ALL.pt')

WHITELIST = {
    'person','bicycle','car','motorcycle','bus','truck',
    'animal','scooter','stroller','dog',
    'pole','post','bollard','utility pole','light pole','signpost',
    'bench','chair','potted plant','hydrant','cone','stone','box',
    'trash can','barrel','cart',
    'fence','barrier','wall','gate','door',
    'rock','tree','branch','curb',
    'stairs','step','ramp','hole',
    'bag','suitcase','backpack',
    'table','ladder','object','obstacle',
    'guide_bricks','crossing_crosswalk',
    'crossing_green_light','crossing_red_light',
    'green_sidewalk','sidewalk',
}

missing = [c for c in m.names.values() if c.lower() not in WHITELIST]
assert not missing, f"白名單缺少類別：{missing}"
print(f"覆蓋率：{len(m.names)}/{len(m.names)} ✓")
```

### YOLOE vs 標準 YOLO 判斷方式

`YOLOE()` 可以成功載入任何標準 YOLO 模型（不會報錯），若未加防護會誤設
`is_yoloe=True`，導致以文字嵌入覆蓋固定類別 → 所有偵測（含 person）全部失效。

**判斷依據**：真正的 YOLOE 模型類別名稱為**純數字**（`'0'`、`'1'`...）；
有具名類別（`'person'`、`'car'`...）即為標準 YOLO，必須走標準路徑。

`obstacle_detector_client.py` 已加防護（載入後立即檢查 class_names 是否全為數字），
**勿移除此檢查**。

---

## YOLO 訓練地雷（必遵守）

1. **Windows 中文路徑禁令**：PyTorch `torch.save()` 在 Windows 無法處理中文路徑。
   - 訓練腳本的 `project=` 輸出路徑**必須是純 ASCII**（如 `runs/`）
   - 資料集、腳本放中文目錄沒事，但訓練輸出不行
   - 違反後果：訓練跑完卻存檔失敗，白費數小時

2. **訓練前必做**：啟動長時間訓練前，先用 1 epoch 測試存檔是否正常
   ```python
   # 先跑 1 epoch 確認存檔沒問題
   model.train(data=..., epochs=1, project="runs/test_save")
   # 確認 runs/test_save/weights/last.pt 存在後再正式訓練
   ```

3. **nohup 啟動**：訓練超過 10 分鐘一律用 `nohup` 啟動，避免 timeout 中斷

## voice map / 語音文字改動後必做

**凡是新增、刪除、或改繁簡體 WAV 檔，必須執行以下全域搜尋，確認所有呼叫點都能命中 map：**

```bash
# 1. 找出所有 play_voice_text / guidance_text 的值
grep -rn "play_voice_text\|guidance_text\s*=" --include="*.py" . | grep -v ".venv" | grep -v "^.*#"

# 2. 確認有無簡體字殘留（凡是 voice map 已換繁體，呼叫點也必須換）
grep -rn "guidance_text\s*=\s*\"" --include="*.py" . | grep -v ".venv" | grep "[^\x00-\x7F]"
```

```python
# 3. 確認所有重要語音 key 都命中 AUDIO_MAP
import audio_player
audio_player._merge_voice_map()
keys_to_check = [/* 從 generate_voice.py PHRASES 複製 */]
for k in keys_to_check:
    stripped = k.rstrip("。！？!?.，,")
    assert stripped in audio_player.AUDIO_MAP, f"未命中：{stripped}"
print("全部命中 ✓")
```

**地雷**：voice map 換繁體後，所有 workflow 的 `guidance_text` 也要同步換成繁體，否則會靜默降級到 TTS fallback（慢 1~2 秒且不易察覺）。

## 任何程式碼改動後的通用規則

**改完就測，不等使用者叫。** 每次修改完畢，立即執行對應測試再回報結果。

## commit 前 → 改用 /pre-commit
