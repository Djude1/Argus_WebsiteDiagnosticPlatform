# -*- coding: utf-8 -*-
import os
import queue
import threading
import math
from array import array
from typing import Any, Optional

import numpy as np

try:
    import audioop
except ImportError:
    audioop = None


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


class MoonshineASRSession:
    def __init__(self, api_key: str, model: str, sample_rate: int, callback: Any):
        del api_key
        os.environ.setdefault(
            "MOONSHINE_VOICE_CACHE",
            os.path.join(os.getcwd(), ".moonshine_cache"),
        )
        self._model = model or os.getenv("MOONSHINE_MODEL", "base")
        self._language = os.getenv("MOONSHINE_LANGUAGE", "zh")
        self._update_interval = float(os.getenv("MOONSHINE_UPDATE_INTERVAL", "0.5"))
        self._sample_rate = sample_rate
        self._cb = callback

        # 读取公共 VAD 参数
        self._vad_rms = int(os.getenv("ASR_VAD_RMS", "140"))
        self._fallback_rms = int(os.getenv("ASR_FALLBACK_RMS", "20"))
        self._end_silence_frames = int(os.getenv("ASR_END_SILENCE_FRAMES", "18"))
        self._debug = os.getenv("ASR_DEBUG", "0") == "1"

        self._running = False
        self._th: Optional[threading.Thread] = None
        self._q: "queue.Queue[Optional[bytes]]" = queue.Queue(maxsize=1024)
        self._last_text = ""

        # VAD 状态
        self._silence_counter = 0
        self._speaking = False

        print(
            f"[ASR CFG] provider=moonshine model={self._model} lang={self._language} "
            f"update_interval={self._update_interval} vad_thr={self._vad_rms} fallback={self._fallback_rms}",
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
        except Exception:
            pass

    def stop(self):
        if not self._running:
            return
        self._running = False
        try:
            self._q.put_nowait(None)
        except Exception:
            pass
        if self._th and self._th.is_alive():
            self._th.join(timeout=2.0)
        try:
            self._cb.on_close()
            self._cb.on_complete()
        except Exception:
            pass

    def send_audio_frame(self, frame: bytes):
        if not self._running or not frame:
            return
        try:
            self._q.put_nowait(frame)
        except queue.Full:
            try:
                _ = self._q.get_nowait()
            except Exception:
                pass
            try:
                self._q.put_nowait(frame)
            except Exception:
                pass

    def _emit_payload(self, text: str, is_final: bool):
        if not text:
            return
        payload = {"sentence": {"text": text.strip(), "sentence_end": bool(is_final)}}
        try:
            self._cb.on_result(payload)
        except Exception:
            try:
                self._cb.on_event(payload)
            except Exception:
                pass

    def _on_transcription_result(self, event: Any):
        line = getattr(event, "line", None)
        text = (getattr(line, "text", "") or "").strip()
        if not text:
            return
        is_final = bool(getattr(line, "is_complete", False))
        if text == self._last_text and (not is_final):
            return
        self._last_text = text
        self._emit_payload(text, is_final)

    @staticmethod
    def _pcm16_to_float32(frame: bytes) -> np.ndarray:
        data = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
        if data.size == 0:
            return np.zeros((0,), dtype=np.float32)
        data /= 32768.0
        return data

    def _calc_rms(self, frame: bytes) -> int:
        """计算音频帧的 RMS 能量"""
        return _rms16_mono(frame)

    def _worker(self):
        stream = None
        transcriber = None
        try:
            from moonshine_voice import ModelArch, Transcriber, get_model_for_language

            arch_map = {
                "tiny": ModelArch.TINY,
                "base": ModelArch.BASE,
                "tiny_streaming": ModelArch.TINY_STREAMING,
                "base_streaming": ModelArch.BASE_STREAMING,
                "small_streaming": ModelArch.SMALL_STREAMING,
                "medium_streaming": ModelArch.MEDIUM_STREAMING,
            }
            wanted_arch = arch_map.get(self._model.lower(), ModelArch.BASE)
            try:
                model_path, model_arch = get_model_for_language(
                    wanted_language=self._language,
                    wanted_model_arch=wanted_arch,
                )
            except Exception:
                model_path, model_arch = get_model_for_language(
                    wanted_language=self._language,
                    wanted_model_arch=None,
                )
            transcriber = Transcriber(
                model_path=model_path,
                model_arch=model_arch,
                update_interval=self._update_interval,
            )
            stream = transcriber.create_stream()
            stream.add_listener(self._on_transcription_result)
            stream.start()
            print(
                f"[ASR] moonshine loaded path='{model_path}' arch={model_arch.name}",
                flush=True,
            )
        except Exception as e:
            print(f"[ASR] moonshine init failed: {e}", flush=True)
            try:
                self._cb.on_error(e)
            except Exception:
                pass
            return

        frame_idx = 0
        try:
            while self._running:
                try:
                    item = self._q.get(timeout=0.2)
                except queue.Empty:
                    item = None

                if item is None:
                    if not self._running:
                        break
                    continue

                frame_idx += 1
                rms = self._calc_rms(item)

                if self._debug and frame_idx % 50 == 0:
                    print(f"[ASR VAD] frame={frame_idx} rms={rms} thr={self._vad_rms} speaking={self._speaking}", flush=True)

                # VAD 决策：只将语音帧送入 Moonshine
                if rms >= self._vad_rms:
                    # 强能量：确定为语音
                    self._speaking = True
                    self._silence_counter = 0
                elif rms >= self._fallback_rms:
                    # 弱能量：如果之前正在说话，则继续；否则丢弃
                    if not self._speaking:
                        continue
                    # 否则继续说话状态
                else:
                    # 静音帧
                    if self._speaking:
                        self._silence_counter += 1
                        # 连续静音过长，重置说话状态并丢弃该帧
                        if self._silence_counter > self._end_silence_frames:
                            self._speaking = False
                            self._silence_counter = 0
                            continue
                    else:
                        # 未说话时的静音，直接丢弃
                        continue

                # 通过 VAD 的帧送入 Moonshine
                try:
                    stream.add_audio(self._pcm16_to_float32(item), self._sample_rate)
                except Exception as e:
                    print(f"[ASR] moonshine stream error: {e}", flush=True)
                    try:
                        self._cb.on_error(e)
                    except Exception:
                        pass
                    break
        finally:
            if stream is not None:
                for fn_name in ("stop", "close"):
                    fn = getattr(stream, fn_name, None)
                    if callable(fn):
                        try:
                            fn()
                        except Exception:
                            pass
            if transcriber is not None:
                try:
                    transcriber.close()
                except Exception:
                    pass