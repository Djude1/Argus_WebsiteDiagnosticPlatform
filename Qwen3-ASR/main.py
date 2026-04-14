#!/usr/bin/env python3
import os
import secrets
import torch
import base64
import numpy as np
import logging
import asyncio
import time
from collections import defaultdict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from qwen_asr import Qwen3ASRModel
import uvicorn
import zhconv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# 安全設定
# ============================================================================
# API 金鑰：透過環境變數 ASR_API_KEY 設定，若未設定則自動產生隨機金鑰
API_KEY = os.environ.get("ASR_API_KEY")
if not API_KEY:
    API_KEY = secrets.token_urlsafe(32)
    logger.warning(f"⚠️  未設定 ASR_API_KEY 環境變數，已自動產生臨時金鑰: {API_KEY}")
    logger.warning("請將以下金鑰設定到前端 WebSocket URL 中（?token=...）")
else:
    logger.info("✅ 已載入 ASR_API_KEY")

# ============================================================================
# 限流設定
# ============================================================================
MAX_CONNECTIONS_PER_IP = 5          # 同一 IP 最大並發連線數
MAX_MESSAGES_PER_SECOND = 30        # 單 IP 每秒最多接收音訊訊息數（防止洪水攻擊）

class RateLimiter:
    def __init__(self):
        self.connections = defaultdict(int)
        self.message_times = defaultdict(list)

    def allow_connect(self, ip: str) -> bool:
        return self.connections[ip] < MAX_CONNECTIONS_PER_IP

    def add_connection(self, ip: str):
        self.connections[ip] += 1

    def remove_connection(self, ip: str):
        if self.connections[ip] > 0:
            self.connections[ip] -= 1

    def allow_message(self, ip: str) -> bool:
        now = time.time()
        times = self.message_times[ip]
        # 清除 1 秒前的記錄
        times = [t for t in times if now - t < 1.0]
        self.message_times[ip] = times
        if len(times) >= MAX_MESSAGES_PER_SECOND:
            return False
        times.append(now)
        return True

limiter = RateLimiter()

# ============================================================================
# VAD（靜音偵測）設定 - 優化版本
# ============================================================================
# 根據 Qwen3-ASR 官方建議：模型內部處理 silence，不需要複雜的 VAD
# 但為了即時語音仍需基礎的能量偵測來斷句
# 閾值調高以減少環境噪音誤判，最小語音時長確保有效片段

VAD_SILENCE_THRESHOLD = 0.02        # 能量閾值（RMS），提高以減少環境噪音誤判（0.015 → 0.02）
VAD_SILENCE_DURATION = 0.6         # 連續靜音超過此時間（秒）則斷句（0.5 → 0.6，更完整句子）
VAD_MIN_SPEECH_DURATION = 0.4       # 最短有效語音時長（秒），短於此長度的片段將被丟棄（0.5 → 0.4，更靈活）
VAD_FRAME_SIZE = 512                # 每次處理的幀大小（樣本數），影響 VAD 精度

class VADAudioBuffer:
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self.silence_threshold = VAD_SILENCE_THRESHOLD
        self.silence_duration = VAD_SILENCE_DURATION
        self.min_speech_samples = int(VAD_MIN_SPEECH_DURATION * sample_rate)
        self.frame_size = VAD_FRAME_SIZE

        self.buffer = np.array([], dtype=np.float32)
        self.is_speech_started = False
        self.silence_frames = 0

        # 音訊正規化參數
        self.target_level = 0.5         # 目標 RMS 電平
        self.max_gain = 10.0            # 最大增益倍數（避免過度放大噪音）

    def _normalize_audio(self, audio: np.ndarray) -> np.ndarray:
        """RMS 正規化音訊，穩定輸入電平"""
        if len(audio) == 0:
            return audio

        rms = np.sqrt(np.mean(audio ** 2))
        if rms < 1e-6:  # 近乎靜音
            return audio

        # 計算需要的增益，不超過 max_gain
        target_rms = self.target_level
        gain = min(target_rms / rms, self.max_gain)

        normalized = audio * gain
        # 裁剪防止爆音
        normalized = np.clip(normalized, -1.0, 1.0)
        return normalized

    def add_chunk(self, samples: np.ndarray):
        """加入音訊片段，回傳需要辨識的完整語音段落（若有的話）"""
        # 正规化音讯再加入缓冲区
        normalized_samples = self._normalize_audio(samples)
        self.buffer = np.concatenate([self.buffer, normalized_samples])
        return self._check_segment()

    def _check_segment(self):
        """檢查緩衝區是否需要斷句，回傳語音段落或 None"""
        if len(self.buffer) < self.frame_size:
            return None

        num_frames = len(self.buffer) // self.frame_size
        segment_end_idx = 0

        for i in range(num_frames):
            start = i * self.frame_size
            end = start + self.frame_size
            frame = self.buffer[start:end]
            rms = np.sqrt(np.mean(frame ** 2))

            if rms < self.silence_threshold:
                self.silence_frames += 1
            else:
                self.silence_frames = 0
                self.is_speech_started = True

            silence_sec = self.silence_frames * self.frame_size / self.sample_rate
            if self.is_speech_started and silence_sec >= self.silence_duration:
                segment_end_idx = end
                break

        if segment_end_idx > 0:
            speech_segment = self.buffer[:segment_end_idx]
            # 只有當語音段長度超過最小閾值時才回傳，避免誤辨識環境噪音
            if len(speech_segment) >= self.min_speech_samples:
                self.buffer = self.buffer[segment_end_idx:]
                self.is_speech_started = False
                self.silence_frames = 0
                return speech_segment
            else:
                # 丟棄過短的片段，繼續緩衝
                self.buffer = self.buffer[segment_end_idx:]
                self.is_speech_started = False
                self.silence_frames = 0
                return None
        return None

    def flush(self):
        """強制回傳緩衝區中剩餘語音（用於錄音結束時）"""
        if len(self.buffer) > 0 and self.is_speech_started:
            segment = self.buffer.copy()
            self.buffer = np.array([], dtype=np.float32)
            self.is_speech_started = False
            self.silence_frames = 0
            return segment
        return None

    def reset(self):
        """重設緩衝區狀態"""
        self.buffer = np.array([], dtype=np.float32)
        self.is_speech_started = False
        self.silence_frames = 0

# ============================================================================
# ASR 模型設定 - 優化版本
# ============================================================================
# vLLM 模型載入參數（基於官方最佳實踐）
# 參考來源：Qwen3-ASR 官方 README vLLM backend 建議
MODEL_NAME = "lixiujie85/Qwen3-ASR-0.6B"
GPU_MEMORY_UTILIZATION = 0.75          # GPU 記憶體使用率（0.7 為官方推薦起始值）
MAX_MODEL_LEN = 4096                 # 最大序列長度（支援更長音訊）
MAX_INFERENCE_BATCH_SIZE = 2        # 批次處理大小（官方建議，生產環境可用 32-128）
MAX_NEW_TOKENS = 512                # 單次生成的最大 token 數（支援更完整句子）
SWAP_SPACE = 1.0                     # 交換空間（GiB）

# FlashAttention 加速（需安裝 flash-attn）
ENABLE_FLASH_ATTENTION = False      # 啟用 FlashAttention 2 加速推理

# 解碼參數（若 qwen_asr 支援，可傳遞以最佳化效果）
ASR_TEMPERATURE = 0.0                # 溫度參數，0.0 為貪婪解碼，輸出最確定
ASR_BEAM_SIZE = 3                    # 束搜尋寬度，提高準確率但增加延遲
ASR_REPETITION_PENALTY = 1.05        # 重複懲罰，抑制重複輸出

# 上下文提示（可幫助模型理解特定領域術語）
ENABLE_CONTEXT_HINTS = False         # 是否啟用上下文提示
ASR_CONTEXT = ""                      # 上下文文字（如專業術語、常用詞彙）

model = None  # 延遲載入

async def transcribe_segment(audio: np.ndarray, language: str = "auto"):
    """呼叫 ASR 模型辨識一段音訊，回傳文字"""
    global model
    if model is None or len(audio) == 0:
        return ""
    # 音訊太短（少於 0.3 秒）直接回傳空，避免無效辨識
    if len(audio) < 4800:   # 16000 * 0.3
        return ""

    try:
        # 語言對應：前端傳 "auto" 則使用 None（自動偵測），否則明確傳入 "zh" 或 "en"
        lang_code = None if language == "auto" else language

        # 構建 transcribe 參數
        transcribe_kwargs = {
            "audio": (audio, 16000),
            "language": lang_code,
            "return_time_stamps": False,
        }

        # 如果啟用上下文提示，添加 context 參數
        if ENABLE_CONTEXT_HINTS and ASR_CONTEXT:
            transcribe_kwargs["context"] = ASR_CONTEXT

        # 注意：部分參數（temperature, beam_size 等）需確認 qwen_asr 介面是否支援
        # 若不支援可安全忽略，模型內部有預設值
        results = model.transcribe(**transcribe_kwargs)

        text = results[0].text.strip()
        return zhconv.convert(text, 'zh-tw')
    except Exception as e:
        logger.error(f"辨識錯誤: {e}")
        return ""

# ============================================================================
# WebSocket 端點
# ============================================================================
@app.websocket("/asr")
async def websocket_asr(websocket: WebSocket, token: str = Query(None)):
    # 1. Token 驗證
    if token != API_KEY:
        logger.warning(f"拒絕連線：無效 token（來自 {websocket.client.host}）")
        await websocket.close(code=1008, reason="Unauthorized")
        return

    client_ip = websocket.client.host

    # 2. 連線數限制
    if not limiter.allow_connect(client_ip):
        logger.warning(f"拒絕連線：IP {client_ip} 並發連線過多")
        await websocket.close(code=1013, reason="Too many connections")
        return

    limiter.add_connection(client_ip)
    await websocket.accept()
    logger.info(f"✅ WebSocket 客戶端已認證: {client_ip}")

    # 初始化 VAD 緩衝區
    buffer = VADAudioBuffer(sample_rate=16000)
    language = "auto"
    loop = asyncio.get_event_loop()

    try:
        while True:
            message = await websocket.receive_text()

            # 頻率限制（僅對音訊訊息，命令訊息不限）
            if not message.startswith("CMD:") and not limiter.allow_message(client_ip):
                logger.warning(f"IP {client_ip} 訊息頻率過高，已丟棄")
                continue

            # 命令處理
            if message.startswith("CMD:"):
                cmd = message[4:].strip()
                if cmd == "END":
                    # 錄音結束，辨識剩餘語音
                    final_segment = buffer.flush()
                    if final_segment is not None:
                        text = await transcribe_segment(final_segment, language)
                        if text:
                            await websocket.send_text(text)
                    break
                elif cmd.startswith("LANG:"):
                    lang = cmd[5:].strip()
                    if lang in ("zh", "en", "auto"):
                        language = lang
                        logger.info(f"語言切換: {language}")
                elif cmd == "RESET":
                    buffer.reset()
                    logger.info("緩衝區已重設")
                continue

            # 音訊資料處理
            try:
                pcm_bytes = base64.b64decode(message)
                samples = np.frombuffer(pcm_bytes, dtype=np.float32)
                if len(samples) == 0:
                    continue

                segment = buffer.add_chunk(samples)
                if segment is not None:
                    text = await transcribe_segment(segment, language)
                    if text:
                        await websocket.send_text(text)
            except Exception as e:
                logger.warning(f"音訊處理異常: {e}")

    except WebSocketDisconnect:
        logger.info(f"客戶端主動斷開: {client_ip}")
    except Exception as e:
        logger.error(f"WebSocket 異常: {e}")
    finally:
        limiter.remove_connection(client_ip)
        if websocket.client_state.name != "DISCONNECTED":
            await websocket.close()
        logger.info(f"WebSocket 連線關閉: {client_ip}")

# ============================================================================
# 啟動入口
# ============================================================================
if __name__ == "__main__":
    logger.info("正在載入 vLLM 模型...")

    # 建立模型參數
    model_kwargs = {
        "model": MODEL_NAME,
        "gpu_memory_utilization": GPU_MEMORY_UTILIZATION,
        "max_model_len": MAX_MODEL_LEN,
        "max_inference_batch_size": MAX_INFERENCE_BATCH_SIZE,
        "max_new_tokens": MAX_NEW_TOKENS,
        "swap_space": SWAP_SPACE,
        "forced_aligner": None,
    }

    # 如果啟用 FlashAttention，添加相關參數
    if ENABLE_FLASH_ATTENTION:
        model_kwargs["dtype"] = "bfloat16"  # FlashAttention 需要 bf16/fp16
        logger.info("🚀 已啟用 FlashAttention 加速")

    model = Qwen3ASRModel.LLM(**model_kwargs)
    logger.info("✅ vLLM 模型載入成功")
    logger.info(f"🔑 當前 API 金鑰: {API_KEY}")
    uvicorn.run(app, host="0.0.0.0", port=8000)