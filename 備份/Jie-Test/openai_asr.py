# -*- coding: utf-8 -*-
import io
import os
import wave
import queue
import threading
from typing import Any, Optional
import math
from array import array

try:
    import audioop
except ImportError:
    audioop = None

from openai import OpenAI


def _rms16_mono(frame: bytes) -> int:
    """计算 16-bit PCM 单声道音频帧的 RMS 能量值"""
    if not frame:
        return 0
    if audioop is not None:
        try:
            return int(audioop.rms(frame, 2))
        except Exception:
            return 0

    try:
        samples = array("h")
        samples.frombytes(frame)
        n = len(samples)
        if n == 0:
            return 0
        energy = sum(s * s for s in samples) / float(n)
        return int(math.sqrt(energy))
    except Exception:
        return 0


class OpenAIASRSession:
    """使用 OpenAI Whisper API 进行实时语音识别的会话类"""

    def __init__(self, api_key: str, model: str, sample_rate: int, callback: Any):
        self._client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )
        self._model = model or os.getenv("OPENAI_ASR_MODEL", "whisper-1")
        self._sample_rate = sample_rate
        self._cb = callback

        self._running = False
        self._th: Optional[threading.Thread] = None
        self._q = queue.Queue(maxsize=512)

        # 从环境变量读取配置
        self._vad_rms = int(os.getenv("OPENAI_ASR_VAD_RMS", "160"))
        self._vad_rms_effective = min(
            self._vad_rms,
            int(os.getenv("OPENAI_ASR_MAX_EFFECTIVE_RMS", "50")),
        )
        self._fallback_rms = int(os.getenv("OPENAI_ASR_FALLBACK_RMS", "12"))
        self._end_silence_frames = int(os.getenv("OPENAI_ASR_END_SILENCE_FRAMES", "10"))
        self._min_speech_ms = int(os.getenv("OPENAI_ASR_MIN_MS", "240"))
        self._force_window_ms = int(os.getenv("OPENAI_ASR_FORCE_WINDOW_MS", "1400"))
        self._debug = os.getenv("OPENAI_ASR_DEBUG", "0") == "1"

        print(
            f"[ASR CFG] model={self._model} vad={self._vad_rms_effective} "
            f"fallback={self._fallback_rms} min_ms={self._min_speech_ms} "
            f"end_frames={self._end_silence_frames} force_ms={self._force_window_ms}",
            flush=True,
        )

    def start(self):
        if self._running:
            return
        self._running = True
        self._th = threading.Thread(target=self._worker, daemon=True)
        self._th.start()
        try:
            self._cb.on_open()
        except AttributeError:
            pass

    def stop(self):
        if not self._running:
            return
        self._running = False
        try:
            self._q.put_nowait(None)
        except queue.Full:
            pass
        if self._th and self._th.is_alive():
            self._th.join(timeout=2.0)
        try:
            self._cb.on_close()
            self._cb.on_complete()
        except AttributeError:
            pass

    def send_audio_frame(self, frame: bytes):
        if not self._running or not frame:
            return
        try:
            self._q.put_nowait(frame)
        except queue.Full:
            # 队列满时丢弃最旧的帧
            try:
                self._q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._q.put_nowait(frame)
            except queue.Full:
                pass

    def _to_wav_bytes(self, pcm16: bytes) -> bytes:
        """将 PCM 数据包装为 WAV 格式的字节流"""
        bio = io.BytesIO()
        with wave.open(bio, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self._sample_rate)
            w.writeframes(pcm16)
        return bio.getvalue()

    def _transcribe_once(self, pcm16: bytes) -> str:
        """调用 OpenAI API 进行一次转录"""
        wav_bytes = self._to_wav_bytes(pcm16)
        f = io.BytesIO(wav_bytes)
        f.name = "speech.wav"
        try:
            resp = self._client.audio.transcriptions.create(
                model=self._model,
                file=f,
                language=os.getenv("OPENAI_ASR_LANGUAGE", "zh"),
            )
            text = getattr(resp, "text", None)
            return (text or "").strip()
        except Exception as e:
            print(f"[ASR] 转录异常: {e}", flush=True)
            return ""

    def _emit_final(self, text: str):
        """通过回调发送最终识别结果"""
        if not text:
            return
        # 构造与 DashScope 兼容的 payload 格式
        payload = {"sentence": {"text": text, "sentence_end": True}}
        try:
            self._cb.on_result(payload)
        except AttributeError:
            try:
                self._cb.on_event(payload)
            except AttributeError:
                pass

    def _worker(self):
        """后台工作线程：处理音频帧，进行 VAD 和语音分段"""
        speech_buf = bytearray()          # 当前语音段的累积缓冲区
        rolling_buf = bytearray()          # 强制窗口缓冲区
        speaking = False                   # 是否正在说话
        silence_frames = 0                  # 连续静音帧计数
        min_bytes = int(self._sample_rate * 2 * (self._min_speech_ms / 1000.0))
        force_bytes = int(self._sample_rate * 2 * (self._force_window_ms / 1000.0))
        weak_hit_streak = 0                 # 连续弱能量帧计数（备用，当前未使用）
        frame_idx = 0

        while self._running:
            try:
                item = self._q.get(timeout=0.2)
            except queue.Empty:
                item = None

            # 超时处理：如果正在说话且缓冲区达到最小长度，强制结束当前段
            if item is None:
                if not self._running:
                    break
                if speaking and len(speech_buf) >= min_bytes:
                    text = self._transcribe_once(bytes(speech_buf))
                    if text:
                        self._emit_final(text)
                speaking = False
                silence_frames = 0
                speech_buf = bytearray()
                continue

            rms = _rms16_mono(item)
            frame_idx += 1
            if self._debug and (frame_idx % 100 == 0):
                print(
                    f"[ASR DEBUG] frame={frame_idx} rms={rms} "
                    f"thr={self._vad_rms_effective} fallback={self._fallback_rms} "
                    f"speaking={speaking} buf={len(speech_buf)} roll={len(rolling_buf)}",
                    flush=True,
                )

            # 强制窗口模式：累积滚动窗口，满长度即转录（用于实时输出）
            if self._force_window_ms > 0:
                rolling_buf.extend(item)
                if len(rolling_buf) >= force_bytes:
                    text = self._transcribe_once(bytes(rolling_buf))
                    if text:
                        self._emit_final(text)
                    rolling_buf = bytearray()

            # VAD 状态机
            if rms >= self._vad_rms_effective:
                # 强能量：开始/继续说话
                if not speaking:
                    speaking = True
                    speech_buf = bytearray()
                speech_buf.extend(item)
                silence_frames = 0
                weak_hit_streak = 0
            elif rms >= self._fallback_rms:
                # 弱能量：如果正在说话则继续累积，否则忽略
                if speaking:
                    speech_buf.extend(item)
                    silence_frames = 0
                weak_hit_streak += 1
            else:
                # 静音帧
                if speaking:
                    speech_buf.extend(item)
                    silence_frames += 1
                    if silence_frames >= self._end_silence_frames:
                        # 连续静音达到阈值，结束当前语音段
                        if len(speech_buf) >= min_bytes:
                            text = self._transcribe_once(bytes(speech_buf))
                            if text:
                                self._emit_final(text)
                        speaking = False
                        silence_frames = 0
                        speech_buf = bytearray()
                weak_hit_streak = 0
