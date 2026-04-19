# asr_core.py
# -*- coding: utf-8 -*-
"""
ASR 核心模組：使用 Google Speech-to-Text 串流 API 進行即時語音辨識。

架構說明：
- GoogleASR 以串流方式即時辨識，有待機/主動雙模式與喚醒詞偵測
- ASRCallback 處理熱詞觸發與 LLM 驅動流程
"""

import os, json, asyncio, io, wave, struct, time, threading, queue, urllib.request, urllib.error
from typing import Any, Dict, List, Optional, Callable, Tuple

ASR_DEBUG_RAW = os.getenv("ASR_DEBUG_RAW", "0") == "1"

# 延遲引入，避免循環依賴（speaker_verifier 在 asr_core 啟動後才初始化）
def _get_speaker_verifier():
    try:
        from speaker_verifier import speaker_verifier
        return speaker_verifier
    except Exception:
        return None

# ── 工具函式 ─────────────────────────────────────────────────────────────────

def _shorten(s: str, limit: int = 200) -> str:
    if not s:
        return ""
    return s if len(s) <= limit else (s[:limit] + "…")

def _calc_rms(pcm_data: bytes) -> float:
    """計算 PCM16 音訊的 RMS 音量值（0 ~ 32767）"""
    if not pcm_data or len(pcm_data) < 2:
        return 0.0
    num_samples = len(pcm_data) // 2
    samples = struct.unpack(f'<{num_samples}h', pcm_data[:num_samples * 2])
    return (sum(s * s for s in samples) / num_samples) ** 0.5

# ── Google SpeechClient 快取（避免每次建立 ASR 都重新初始化 gRPC）──────────────
_cached_speech_client = None
_cached_speech_client_lock = threading.Lock()

def _get_or_create_speech_client(credentials_path: str):
    """取得或建立共用的 SpeechClient，首次呼叫會建立 gRPC 連線（較慢），後續直接複用。"""
    global _cached_speech_client
    if _cached_speech_client is not None:
        return _cached_speech_client
    with _cached_speech_client_lock:
        if _cached_speech_client is not None:
            return _cached_speech_client
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        from google.cloud import speech as _speech
        t0 = time.monotonic()
        _cached_speech_client = _speech.SpeechClient()
        elapsed = time.monotonic() - t0
        print(f"[GoogleASR] SpeechClient 已建立（耗時 {elapsed:.1f}s）", flush=True)
        return _cached_speech_client

def preload_speech_client(credentials_path: str):
    """伺服器啟動時呼叫，背景預載 SpeechClient，縮短首次語音辨識等待時間。"""
    def _worker():
        _get_or_create_speech_client(credentials_path)
    threading.Thread(target=_worker, daemon=True, name="PreloadSpeechClient").start()

def _normalize_cn(s: str) -> str:
    try:
        import unicodedata
        s = "".join(" " if unicodedata.category(ch) == "Zs" else ch for ch in s)
        s = s.strip().lower()
    except Exception:
        s = (s or "").strip().lower()
    return s

# 麥克風增益倍數（放大 ESP32 麥克風訊號，預設 5 倍；可在 .env 設定 ASR_PCM_GAIN）
# 建議範圍：3.0（保守）~ 10.0（最大收音）；過高會 clip 但 ASR 仍可辨識
PCM_GAIN = float(os.getenv("ASR_PCM_GAIN", "5.0"))

# 待機模式送出批次前的 RMS 音量門檻（低於此值視為靜音，不送 ASR 節省費用）
# 降低此值可收到更小聲的喚醒詞，但也可能誤送環境噪音
# 預設 150（比原來 300 更靈敏）；可在 .env 設定 ASR_STANDBY_RMS_THRESH
STANDBY_RMS_THRESH = float(os.getenv("ASR_STANDBY_RMS_THRESH", "150.0"))

def _pcm_to_wav(pcm_data: bytes, sample_rate: int = 16000,
                channels: int = 1, sampwidth: int = 2) -> bytes:
    """將原始 PCM16 資料包裝為 WAV 格式，並套用增益補償"""
    if PCM_GAIN != 1.0:
        n = len(pcm_data) // 2
        samples = struct.unpack(f'<{n}h', pcm_data[:n * 2])
        pcm_data = struct.pack(
            f'<{n}h',
            *(max(-32768, min(32767, int(s * PCM_GAIN))) for s in samples)
        )
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return buf.getvalue()

# ── 熱詞設定 ─────────────────────────────────────────────────────────────────

INTERRUPT_KEYWORDS = set(
    os.getenv("INTERRUPT_KEYWORDS", "停下所有功能,停止所有功能").split(",")
)

# ── 喚醒詞 / 結束詞設定 ──────────────────────────────────────────────────────
WAKE_WORDS = set(os.getenv("WAKE_WORDS", (
    # 標準喚醒詞
    "哈囉 曼波,哈囉曼波,哈囉，曼波,哈喽曼波,哈喽漫播,哈喽 曼波,哈喽，曼波,"
    # ASR 誤辨常見變體（含「羅曼波」可涵蓋「阿羅曼波」「沙羅曼波」）
    "羅曼波,哈囉慢播,哈囉嗎"
)).split(","))
END_WORDS  = set(os.getenv("END_WORDS",  "謝謝 曼波,謝謝曼波,謝謝，曼波,谢谢曼波,谢谢漫播,谢谢 曼波").split(","))

# ── ASR 全局總閘 ─────────────────────────────────────────────────────────────

_current_recognition: Optional[object] = None
_rec_lock = asyncio.Lock()

# ── 旁路模式：跳過喚醒詞，所有 STT 結果直接派發 ──────────────────────────────
_bypass_wake: bool = False

def set_bypass_wake(enabled: bool):
    global _bypass_wake
    _bypass_wake = enabled
    status = "開啟" if enabled else "關閉"
    print(f"[ASR] 旁路模式（跳過喚醒詞）已{status}", flush=True)

def get_bypass_wake() -> bool:
    return _bypass_wake

async def set_current_recognition(r):
    global _current_recognition
    async with _rec_lock:
        _current_recognition = r

async def stop_current_recognition():
    global _current_recognition
    async with _rec_lock:
        r = _current_recognition
        _current_recognition = None
    if r:
        try:
            r.stop()
        except Exception:
            pass

# ── ASRCallback ──────────────────────────────────────────────────────────────

class ASRCallback:
    """
    設計目標：
    1) 「停下 / 別說了 …」等熱詞一出現 → 立刻全清零重置。
    2) AI 正在播報時，用戶語音只做展示，不觸發新一輪。
    3) 只有 final sentence 用於驅動 AI。
    """

    def __init__(
        self,
        on_sdk_error: Callable[[str], None],
        post: Callable[[asyncio.Future], None],
        ui_broadcast_partial,
        ui_broadcast_final,
        is_playing_now_fn: Callable[[], bool],
        start_ai_with_text_fn,
        full_system_reset_fn,
        interrupt_lock: asyncio.Lock,
        on_wake_fn:           Optional[Callable] = None,
        on_end_fn:            Optional[Callable] = None,
        on_recording_end_fn:  Optional[Callable] = None,
    ):
        self._on_sdk_error = on_sdk_error
        self._post = post
        self._ui_partial = ui_broadcast_partial
        self._ui_final   = ui_broadcast_final
        self._is_playing = is_playing_now_fn
        self._start_ai   = start_ai_with_text_fn
        self._full_reset = full_system_reset_fn
        self._interrupt_lock = interrupt_lock
        self._hot_interrupted: bool = False
        self._ai_dispatched:   bool = False           # 是否已派發 AI 處理（用於避免重複播 結束收音）
        self._rec_end_played:  bool = False           # 結束收音音效是否已提前播放
        self._on_wake          = on_wake_fn           # 喚醒詞觸發（播放「開始對話」）
        self._on_end           = on_end_fn            # 結束詞「謝謝曼波」觸發（播放「結束對話」）
        self._on_recording_end = on_recording_end_fn  # 主動錄音自然結束（播放「結束收音」）

    def on_open(self):  pass
    def on_close(self): pass
    def on_complete(self): pass

    def on_wake(self):
        """喚醒詞觸發：播放開始對話音效"""
        if self._on_wake:
            try:
                self._on_wake()
            except Exception:
                pass

    def on_end_word(self):
        """結束詞「謝謝曼波」觸發：播放結束對話音效"""
        if self._on_end:
            try:
                self._on_end()
            except Exception:
                pass

    def play_recording_end_sound(self):
        """立即播放結束收音音效（轉錄前呼叫，讓音效即時播出）"""
        self._rec_end_played = True
        if self._on_recording_end:
            try:
                self._on_recording_end()
            except Exception:
                pass

    def on_recording_end(self):
        """主動錄音自然結束（靜音/超時）：
        若之前已派發 AI 處理（用戶說了指令），跳過；
        否則（用戶沉默未說話）才播放結束收音音效。
        """
        if self._ai_dispatched:
            # 已在 _run_final 播過 結束收音，重置旗標即可
            self._ai_dispatched = False
            return
        if self._on_recording_end:
            try:
                self._on_recording_end()
            except Exception:
                pass

    def on_error(self, err):
        try:
            self._post(self._ui_partial(""))
            self._on_sdk_error(str(err))
        except Exception:
            pass

    def on_result(self, result): self._handle(result)
    def on_event(self,  event):  self._handle(event)

    def _has_hotword(self, text: str) -> bool:
        t = _normalize_cn(text)
        if not t:
            return False
        for w in INTERRUPT_KEYWORDS:
            if w and _normalize_cn(w) in t:
                return True
        return False

    def _handle(self, event: Any):
        # 解析事件
        if isinstance(event, dict):
            d = event
        else:
            return

        # 向下挖掘 sentence 結構
        text, is_end = None, None
        sentence = (d.get("output") or {}).get("sentence") or d.get("sentence")
        if isinstance(sentence, dict):
            text   = sentence.get("text")
            is_end = sentence.get("sentence_end")
            if is_end is not None:
                is_end = bool(is_end)

        if text is None or not text.strip():
            return
        text = text.strip()

        if ASR_DEBUG_RAW:
            print(f"[ASR EVENT] text='{_shorten(text)}' is_end={is_end}", flush=True)

        # ① 熱詞優先：命中就全清零並短路
        if not self._hot_interrupted and self._has_hotword(text):
            self._hot_interrupted = True

            async def _hot_reset():
                async with self._interrupt_lock:
                    print(f"[ASR HOTWORD] '{text}' -> FULL RESET", flush=True)
                    await self._full_reset("Hotword interrupt")
            try:
                self._post(_hot_reset())
            except Exception:
                pass
            return

        # ② 展示給 UI
        try:
            print(f"[ASR PARTIAL] '{_shorten(text)}'", flush=True)
            self._post(self._ui_partial(text))
        except Exception:
            pass

        # ③ final 驅動 LLM
        if is_end is True:
            final_text = text
            try:
                print(f"[ASR FINAL] '{final_text}'", flush=True)
                self._post(self._ui_final(final_text))
            except Exception:
                pass

            if (not self._is_playing()) and final_text:
                self._ai_dispatched = True
                on_rec_end = self._on_recording_end

                async def _run_final():
                    # 同時播放結束收音音效 + 啟動 AI，兩者並行互不等待
                    async def _play_sound():
                        if self._rec_end_played:
                            # 已提前播過，不重複播
                            self._rec_end_played = False
                            return
                        if on_rec_end:
                            try:
                                on_rec_end()
                            except Exception:
                                pass

                    async def _call_ai():
                        async with self._interrupt_lock:
                            print(f"[LLM INPUT TEXT] {final_text}", flush=True)
                            await self._start_ai(final_text)

                    await asyncio.gather(_play_sound(), _call_ai())
                try:
                    self._post(_run_final())
                except Exception:
                    self._ai_dispatched = False

            self._hot_interrupted = False

# ── GoogleASR：使用 Google Speech-to-Text 串流 API ───────────────────────────

class GoogleASR:
    """
    使用 Google Speech-to-Text 串流 API 的即時 ASR。
    介面：start() / stop() / send_audio_frame()

    運作模式：
    - 待機模式（standby）：持續串流，偵測喚醒詞「哈囉曼波」
    - 主動模式（active）：收到喚醒詞後啟動，靜音超過 SILENCE_SEC 即結束並派發指令
    """

    SILENCE_SEC:        float = 2.5    # 主動模式靜音判斷秒數（延長避免截斷指令）
    SILENCE_RMS_THRESH: float = 150.0  # RMS 低於此值視為靜音（已調低提升靈敏度）
    ACTIVE_MAX_SEC:     float = 12.0   # 主動模式最長錄音時間
    STREAM_RESTART_SEC: float = 200.0  # Google 串流 5 分鐘上限，提前重啟
    # 說話人驗證用的近期音訊緩衝（滑動視窗保留最近 N 秒音訊）
    _RECENT_BUF_SEC:    float = 5.0    # 保留最近 5 秒供聲紋比對

    # 喚醒詞寬鬆比對關鍵字（只要「哈囉」即可觸發，不需要「曼波」）
    _HELLO_VARIANTS = ("哈囉", "哈喽", "哈啰")

    def __init__(self, credentials_path: str, sample_rate: int, callback: "ASRCallback",
                 bypass_wake: bool = False):
        self._credentials_path = credentials_path
        self._sample_rate      = sample_rate
        self._callback         = callback
        self._bypass_wake      = bypass_wake   # 實例級旁路模式（APP 連線時啟用）
        self._running          = False
        self._audio_queue: queue.Queue = queue.Queue()
        self._mode             = "standby"
        self._last_voice_ts    = 0.0
        self._active_start     = 0.0
        self._stream_thread: Optional[threading.Thread] = None

        # 近期音訊滑動緩衝（用於說話人驗證）
        self._recent_buf      = bytearray()
        self._recent_max_bytes = int(self._RECENT_BUF_SEC * sample_rate * 2)  # PCM16
        self._recent_lock     = threading.Lock()

    def start(self):
        self._running   = True
        self._mode      = "standby"
        self._audio_queue = queue.Queue()
        try:
            self._loop = asyncio.get_event_loop()
        except RuntimeError:
            self._loop = None
        self._stream_thread = threading.Thread(
            target=self._stream_loop, daemon=True, name="GoogleASR"
        )
        self._stream_thread.start()
        if self._bypass_wake:
            print("[GoogleASR] started（旁路模式，跳過喚醒詞）", flush=True)
        else:
            print("[GoogleASR] started（待機中，等待喚醒詞）", flush=True)

    def stop(self):
        self._running = False
        self._audio_queue.put(None)  # sentinel，讓 generator 結束
        print("[GoogleASR] stopped", flush=True)

    def enter_active_mode(self):
        self._mode = "active"
        now = time.monotonic()
        self._active_start  = now
        self._last_voice_ts = now
        print("[GoogleASR] 進入主動錄音模式，等待指令…", flush=True)

    def send_audio_frame(self, data: bytes):
        if not self._running:
            return

        # 套用麥克風增益（補償 ESP32 麥克風音量不足）
        if PCM_GAIN != 1.0:
            n = len(data) // 2
            if n > 0:
                samples = struct.unpack(f'<{n}h', data[:n * 2])
                data = struct.pack(
                    f'<{n}h',
                    *(max(-32768, min(32767, int(s * PCM_GAIN))) for s in samples)
                )

        # 維護近期音訊滑動緩衝（供說話人驗證使用）
        with self._recent_lock:
            self._recent_buf.extend(data)
            if len(self._recent_buf) > self._recent_max_bytes:
                # 保留最新的 N 秒音訊
                self._recent_buf = self._recent_buf[-self._recent_max_bytes:]

        self._audio_queue.put(data)
        if self._mode == "active" and _calc_rms(data) > self.SILENCE_RMS_THRESH:
            self._last_voice_ts = time.monotonic()

    # ── 內部方法 ────────────────────────────────────────────────────────────

    def _audio_generator(self, stop_event: threading.Event):

        """從 queue 持續讀取音訊 chunk，產生 StreamingRecognizeRequest。
        佇列空時送靜音填充，避免 Google STT 因無音訊而 timeout 斷線。"""
        from google.cloud import speech as _speech
        stream_start = time.monotonic()
        # 100ms 靜音填充（16000 Hz * 2 bytes * 0.1s）
        silence_chunk = bytes(int(self._sample_rate * 2 * 0.1))
        while self._running and not stop_event.is_set():
            # 超過時間上限，結束此 generator 讓串流重啟
            if time.monotonic() - stream_start >= self.STREAM_RESTART_SEC:
                return
            try:
                chunk = self._audio_queue.get(timeout=0.1)
                if chunk is None:
                    return
                yield _speech.StreamingRecognizeRequest(audio_content=chunk)
            except queue.Empty:
                # 佇列空：送靜音保持串流活躍
                yield _speech.StreamingRecognizeRequest(audio_content=silence_chunk)

    def _handle_result(self, transcript: str, is_final: bool):
        """統一處理 Google STT 結果"""
        if self._mode == "standby":
            if not is_final:
                return
            print(f"[GoogleASR] 待機辨識: '{transcript}'", flush=True)
            self._check_wake_word(transcript)
        else:
            # 主動模式：即時顯示 partial，final 派發指令
            self._handle_active(transcript, is_final)
            # 靜音 / 超時 → 切回待機
            now = time.monotonic()
            if (now - self._last_voice_ts >= self.SILENCE_SEC or
                    now - self._active_start >= self.ACTIVE_MAX_SEC):
                reason = "靜音" if now - self._last_voice_ts >= self.SILENCE_SEC else "超時"
                print(f"[GoogleASR] 主動模式結束（{reason}）", flush=True)
                self._mode = "standby"
                self._callback.on_recording_end()  # 播放「結束收音」音效

    def _check_wake_word(self, text: str):
        # 旁路模式（全域或實例級）：跳過喚醒詞，STT 結果直接派發給 AI
        if _bypass_wake or self._bypass_wake:
            print(f"[ASR-旁路] STT → '{text}'", flush=True)
            event = {"output": {"sentence": {"text": text, "sentence_end": True}}}
            self._callback.on_event(event)
            return

        norm = _normalize_cn(text)
        matched = any(w and _normalize_cn(w) in norm for w in WAKE_WORDS)
        if not matched:
            # 只要辨識到「哈囉」即可觸發喚醒
            matched = any(v in norm for v in self._HELLO_VARIANTS)

        if not matched:
            print(f"[GoogleASR] 待機中收到: '{text}'（無喚醒詞，忽略）", flush=True)
            return

        # 喚醒詞命中 → 說話人驗證（用近期緩衝音訊）
        sv = _get_speaker_verifier()
        if sv and sv.is_enabled():
            with self._recent_lock:
                recent_audio = bytes(self._recent_buf)
            if not sv.verify(recent_audio, self._sample_rate):
                print(f"[GoogleASR] 喚醒詞命中但說話人不符，忽略: '{text}'", flush=True)
                return

        print(f"[GoogleASR] 喚醒詞偵測: '{text}'", flush=True)
        self._callback.on_wake()
        self.enter_active_mode()

    def _handle_active(self, text: str, is_final: bool):
        norm = _normalize_cn(text)
        # 結束詞偵測
        if is_final:
            for w in END_WORDS:
                if w and _normalize_cn(w) in norm:
                    print(f"[GoogleASR] 結束詞偵測: '{text}'", flush=True)
                    self._mode = "standby"
                    self._callback.on_end_word()
                    return
        event = {"output": {"sentence": {"text": text, "sentence_end": is_final}}}
        self._callback.on_event(event)

    def _stream_loop(self):
        """主串流執行緒：含自動重啟邏輯"""

        from google.cloud import speech as _speech

        config = _speech.RecognitionConfig(
            encoding=_speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=self._sample_rate,
            language_code="cmn-Hant-TW",
            alternative_language_codes=["zh-CN"],
            enable_automatic_punctuation=True,
            # 熱詞：提高「曼波」相關詞的辨識權重
            speech_contexts=[_speech.SpeechContext(
                phrases=["哈囉曼波", "哈囉 曼波", "謝謝曼波", "謝謝 曼波",
                         "羅曼波", "哈囉慢播", "哈囉嗎",
                         "曼波", "漫波", "漫播", "慢播"],
                boost=20.0,
            )],
        )
        streaming_config = _speech.StreamingRecognitionConfig(
            config=config,
            interim_results=True,
        )

        # 複用快取的 SpeechClient（伺服器啟動時已預載）
        client = _get_or_create_speech_client(self._credentials_path)

        while self._running:
            stop_event = threading.Event()
            try:
                responses = client.streaming_recognize(
                    streaming_config,
                    self._audio_generator(stop_event),
                )
                for response in responses:
                    if not self._running:
                        break
                    for result in response.results:
                        if not result.alternatives:
                            continue
                        transcript = result.alternatives[0].transcript.strip()
                        self._handle_result(transcript, result.is_final)
            except Exception as e:
                if self._running:
                    print(f"[GoogleASR] 串流錯誤: {e}，2 秒後重啟", flush=True)
                    time.sleep(2)
            finally:
                stop_event.set()


# ── 動態參數調整（Dashboard 用，不重啟生效）────────────────────────────────────

def set_standby_rms_thresh(value: float):
    """設定待機靜音門檻（低於此 RMS 不送 ASR）"""
    global STANDBY_RMS_THRESH
    STANDBY_RMS_THRESH = float(value)

def set_pcm_gain(value: float):
    """設定麥克風增益倍數"""
    global PCM_GAIN
    PCM_GAIN = float(value)

def set_silence_sec(value: float):
    """設定主動模式靜音判斷秒數"""
    GoogleASR.SILENCE_SEC = float(value)

def set_silence_rms_thresh(value: float):
    """設定主動模式靜音 RMS 門檻"""
    GoogleASR.SILENCE_RMS_THRESH = float(value)
