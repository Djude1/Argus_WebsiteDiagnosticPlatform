# Qwen3-ASR WebSocket 語音識別服務

## 一、服務基本信息

| 項目 | 值 |
| --- | --- |
| **訪問地址** | `wss://asr.clouda.dpdns.org/asr?token=<token>` |
| **協議** | WebSocket (WSS) |
| **端點** | `/asr` |
| **認證方式** | URL Query 參數 `token` |
| **默認端口** | 8000 |
| **模型** | Qwen3-ASR |

---

## 二、WebSocket 連接

### 連接格式

```
wss://[主機地址]/asr?token=[你的API金鑰]
```

### 示例 (JavaScript)

```jsx
const ws = new WebSocket('wss://asr.clouda.dpdns.org/asr?token=33899');

ws.onopen = () => {
    console.log('✅ ASR 服務已連接');
};

ws.onmessage = (event) => {
    console.log('識別結果:', event.data);
};

ws.onerror = (error) => {
    console.error('❌ WebSocket 錯誤:', error);
};

ws.onclose = (event) => {
    console.log('連線已關閉:', event.code, event.reason);
};
```

---

## 三、音頻格式與前端處理

為了確保與服務端完美適配，請嚴格按照以下方式處理麥克風音頻數據。

### 3.1 核心音頻參數

| 參數 | 必須嚴格遵守的值 | 說明 |
| --- | --- | --- |
| **採樣率 (Sample Rate)** | **16000 Hz** | 必須在 `AudioContext` 建立時指定。 |
| **聲道數 (Channels)** | **1 (Mono)** | 單聲道輸入。 |
| **數據類型** | **Float32Array** | 從 `AudioBuffer` 取得的原始數據。 |
| **傳輸編碼** | **Base64** | 將 Float32Array 的底層 `ArrayBuffer` 直接轉換為 Base64 字串。 |
| **發送間隔** | **每 250ms** | 將這段時間內累積的音頻幀合併後一次性發送。 |

### 3.2 麥克風初始化 (啟用硬體降噪)

首先請求麥克風權限，建議開啟瀏覽器內建的降噪與回音消除功能以提升辨識率。

```jsx
const TARGET_SAMPLE_RATE = 16000;

const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
        sampleRate: TARGET_SAMPLE_RATE,
        channelCount: 1,
        echoCancellation: true,   // 回音消除
        noiseSuppression: true,   // 降噪
        autoGainControl: true     // 自動增益
    }
});

// 建立音頻上下文，強制設定採樣率
const audioContext = new (window.AudioContext || window.webkitAudioContext)({
    sampleRate: TARGET_SAMPLE_RATE
});
```

### 3.3 音頻捕獲與緩衝 (ScriptProcessorNode)

使用 `ScriptProcessorNode` 捕獲實時音頻流。**請注意**：服務端採用 VAD 流式處理，因此不要在此處進行手動重採樣或位深度轉換。

```jsx
const sourceNode = audioContext.createMediaStreamSource(stream);
const processorNode = audioContext.createScriptProcessor(4096, 1, 1);

let pcmBuffer = []; // 用於累積 Float32Array 片段的陣列

processorNode.onaudioprocess = (event) => {
    // 僅在錄音狀態下收集數據
    if (!isRecording) return;

    // 獲取 Float32 格式的原始音頻數據
    const inputData = event.inputBuffer.getChannelData(0);

    // 複製一份存入緩衝區 (避免底層緩衝被覆蓋)
    pcmBuffer.push(new Float32Array(inputData));
};

sourceNode.connect(processorNode);
processorNode.connect(audioContext.destination); // 必須連接以觸發處理
```

### 3.4 數據發送 (Base64 編碼)

服務端期望接收 **Float32Array 原始位元組的 Base64 字串**。請定時調用以下函數發送數據。

```jsx
const CHUNK_DURATION = 0.25; // 250ms 發送一次

function sendPcmChunk() {
    if (!isRecording || pcmBuffer.length === 0) return;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    // 1. 計算總長度並合併緩衝區中的所有 Float32Array
    let totalLen = pcmBuffer.reduce((sum, arr) => sum + arr.length, 0);
    let combined = new Float32Array(totalLen);
    let offset = 0;
    for (let arr of pcmBuffer) {
        combined.set(arr, offset);
        offset += arr.length;
    }

    // 2. 清空已處理的緩衝
    pcmBuffer = [];

    // 3. 獲取底層 ArrayBuffer 並轉為 Base64
    const bytes = new Uint8Array(combined.buffer);
    // 使用展開運算符轉換為字串編碼 (注意：大數據量建議分批處理，此處因每次約 4000 樣本點，性能無虞)
    const base64 = btoa(String.fromCharCode(...bytes));

    // 4. 通過 WebSocket 發送
    ws.send(base64);
}

// 啟動定時發送器
const sendInterval = setInterval(sendPcmChunk, CHUNK_DURATION * 1000);
```

### 3.5 關鍵提醒

- **嚴禁轉換為 Int16**：請直接發送 Float32 位元組。服務端使用 `np.frombuffer(data, dtype=np.float32)` 解析，若發送 Int16 數據將導致聲音振幅異常，無法辨識。
- **確保 AudioContext 已恢復**：由於瀏覽器自動播放策略，請在用戶點擊按鈕時調用 `audioContext.resume()`。
- **停止錄音時的收尾**：停止錄音前，務必調用一次 `sendPcmChunk()` 發送最後剩餘的數據，並發送命令 `CMD:END`。

```jsx
function stopRecording() {
    clearInterval(sendInterval);
    sendPcmChunk(); // 發送最後一包殘留數據
    ws.send('CMD:END');
    isRecording = false;
}
```

以上就是基於您提供的 `index.html` 前端的標準實現。遵循此流程即可無縫接入 Qwen3-ASR 服務。

---

## 四、命令協議

服務支持以下命令格式，以 `CMD:` 開頭：

### 1. 結束錄音 - `CMD:END`

通知服務端錄音結束，強制識別緩衝區中剩餘的音頻：

```jsx
ws.send('CMD:END');
```

**響應**：服務端會返回最終識別結果文本

### 2. 設置語言 - `CMD:LANG:`

設置識別語言，支持 `zh`（中文）、`en`（英文）、`auto`（自動）：

```jsx
ws.send('CMD:LANG:zh');   // 強制中文
ws.send('CMD:LANG:en');   // 強制英文
ws.send('CMD:LANG:auto'); // 自動檢測（默認）
```

### 3. 重置緩衝區 - `CMD:RESET`

清空音頻緩衝區，重新開始識別：

```jsx
ws.send('CMD:RESET');
```

---

## 五、通訊流程示例

### 完整識別流程

```jsx
const ws = new WebSocket('wss://asr.clouda.dpdns.org/asr?token=33899');

ws.onopen = () => {
    // 1. 設置語言（可選）
    ws.send('CMD:LANG:zh');

    // 2. 開始錄音並發送音頻數據
    startRecordingAndSend(ws);
};

ws.onmessage = (event) => {
    // 3. 實時接收識別結果
    if (!event.data.startsWith('CMD:')) {
        console.log('識別結果:', event.data);
    }
};

// 結束錄音
function stopRecording(ws) {
    ws.send('CMD:END');
    // 等待識別結果後再關閉連接
    setTimeout(() => ws.close(), 1000);
}
```

### 實時語音識別模式

```jsx
// 每隔一段時間發送音頻塊
setInterval(() => {
    const audioChunk = getAudioChunk(); // 獲取最近的分析結果
    if (audioChunk && ws.readyState === WebSocket.OPEN) {
        const base64 = audioToBase64(audioChunk);
        ws.send(base64);
    }
}, 250); // 250ms 發送一次
```

---

## 六、VAD（語音活動檢測）配置

服務端已內置 VAD 參數，控制語音斷句：

| 參數 | 當前值 | 說明 |
| --- | --- | --- |
| `VAD_SILENCE_THRESHOLD` | 0.015 | 能量閾值，低於此值視為靜音 |
| `VAD_SILENCE_DURATION` | 0.5s | 連續靜音超過此時長則斷句 |
| `VAD_MIN_SPEECH_DURATION` | 0.5s | 最短有效語音時長 |

> 如果環境噪音較大，可適當提高閾值（如 0.02），但需修改服務端代碼。
> 

---

## 七、錯誤處理

### WebSocket 錯誤碼

| 錯誤碼 | 含義 |
| --- | --- |
| 1000 | 正常關閉 |
| 1006 | 服務端內部異常（請檢查後台日誌） |
| 1008 | Token 無效或未提供 |
| 1013 | 同 IP 並發連線過多（>5） |

### 常見問題排查

**1. 連接被拒絕 (1008)**

- 檢查 `token` 參數是否正確
- 確認服務端的 `ASR_API_KEY` 環境變數

**2. 沒有識別結果**

- 確認音頻格式是否為 16kHz Float32
- 檢查音量是否過低（低於 VAD 閾值）
- 嘗試發送 `CMD:END` 強制輸出結果

**3. 識別結果為空**

- 音頻過短（少於 0.3 秒）
- 語言設置與音頻不匹配

---

## 八、Python 客戶端示例

```python
import asyncio
import json
import base64
import websockets
import numpy as np
import soundfile as sf

async def asr_client():
    uri = "wss://asr.clouda.dpdns.org/asr?token=33899"

    async with websockets.connect(uri) as ws:
        # 讀取音頻文件
        audio, samplerate = sf.read("test.wav", dtype='float32')

        # 重採樣至 16kHz（如需要）
        if samplerate != 16000:
            # 使用 librosa 重採樣
            import librosa
            audio = librosa.resample(audio, orig_sr=samplerate, target_sr=16000)

        # 發送音頻數據
        audio_bytes = audio.tobytes()
        b64_audio = base64.b64encode(audio_bytes).decode('utf-8')
        await ws.send(b64_audio)

        # 發送結束命令
        await ws.send("CMD:END")

        # 接收結果
        result = await ws.recv()
        print(f"識別結果: {result}")

asyncio.run(asr_client())
```

---

## 九、服務端配置參數

如需修改服務行為，可調整 `main.py` 中的以下參數：

```python
# 模型配置
MODEL_NAME = "lixiujie85/Qwen3-ASR"  # 模型名稱
GPU_MEMORY_UTILIZATION = 0.75              # GPU 記憶體使用率
MAX_MODEL_LEN = 4096                       # 最大序列長度
MAX_NEW_TOKENS = 512                       # 生成的最大 token 數

# 安全配置
MAX_CONNECTIONS_PER_IP = 5                 # 單 IP 最大並發連線
MAX_MESSAGES_PER_SECOND = 30               # 單 IP 每秒最大訊息數

# VAD 配置
VAD_SILENCE_THRESHOLD = 0.02              # 能量閾值
VAD_SILENCE_DURATION = 0.5                # 靜音斷句時長
VAD_MIN_SPEECH_DURATION = 0.5             # 最短語音時長
```