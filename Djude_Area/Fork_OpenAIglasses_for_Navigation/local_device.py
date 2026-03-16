# local_device.py
# -*- coding: utf-8 -*-
"""
本機模式（LOCAL_MODE=true）：以電腦的攝影機、麥克風、喇叭取代 ESP32。
啟用方式：在 .env 設定 LOCAL_MODE=true，重啟伺服器即生效。
"""

import os
import time
import queue
import threading
import cv2
import numpy as np
import bridge_io

# ── 設定讀取 ────────────────────────────────────────────────────────────────
LOCAL_MODE      = os.getenv("LOCAL_MODE", "false").lower() == "true"
SAMPLE_RATE     = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
CHUNK_MS        = int(os.getenv("AUDIO_CHUNK_MS", "20"))
CAM_INDEX       = int(os.getenv("CAM_INDEX", "0"))
JPEG_QUALITY    = int(os.getenv("LOCAL_CAM_QUALITY", "70"))
STREAM_SR       = 8000  # 與 audio_stream.py STREAM_SR 一致

_stop_event = threading.Event()

# ── 攝影機輸入 ──────────────────────────────────────────────────────────────

def _webcam_loop():
    cap = cv2.VideoCapture(CAM_INDEX)
    if not cap.isOpened():
        print(f"[LOCAL-CAM] 無法開啟攝影機 index={CAM_INDEX}", flush=True)
        return
    print(f"[LOCAL-CAM] 本機攝影機已啟動（index={CAM_INDEX}）", flush=True)
    while not _stop_event.is_set():
        ret, frame = cap.read()
        if ret:
            ok, jpg = cv2.imencode(
                ".jpg", frame,
                [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
            )
            if ok:
                bridge_io.push_raw_jpeg(jpg.tobytes())
        else:
            time.sleep(0.01)
    cap.release()
    print("[LOCAL-CAM] 攝影機已停止", flush=True)


# ── 麥克風輸入 ──────────────────────────────────────────────────────────────

_mic_recognition = None
_mic_lock = threading.Lock()


def set_local_recognition(rec):
    """由 app_main.py 在建立 ASR 物件後呼叫，讓麥克風執行緒知道要送到哪裡。"""
    global _mic_recognition
    with _mic_lock:
        _mic_recognition = rec


def _mic_loop():
    import pyaudio
    pa = pyaudio.PyAudio()
    chunk_frames = SAMPLE_RATE * CHUNK_MS // 1000   # 16000*20//1000 = 320 samples
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=chunk_frames,
    )
    print("[LOCAL-MIC] 本機麥克風已啟動", flush=True)
    while not _stop_event.is_set():
        try:
            data = stream.read(chunk_frames, exception_on_overflow=False)
        except Exception:
            continue
        with _mic_lock:
            rec = _mic_recognition
        if rec is not None:
            try:
                rec.input(data)
            except Exception:
                pass
    stream.stop_stream()
    stream.close()
    pa.terminate()
    print("[LOCAL-MIC] 麥克風已停止", flush=True)


# ── 本機喇叭輸出 ────────────────────────────────────────────────────────────

_speaker_queue: "queue.Queue[bytes | None]" = queue.Queue(maxsize=200)
_speaker_thread: threading.Thread | None = None


def _speaker_loop():
    import pyaudio
    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=STREAM_SR,
        output=True,
        frames_per_buffer=STREAM_SR * CHUNK_MS // 1000,
    )
    print(f"[LOCAL-SPK] 本機喇叭已啟動（{STREAM_SR} Hz）", flush=True)
    while True:
        try:
            chunk = _speaker_queue.get(timeout=0.5)
        except queue.Empty:
            if _stop_event.is_set():
                break
            continue
        if chunk is None:   # 停止訊號
            break
        try:
            stream.write(chunk)
        except Exception:
            pass
    stream.stop_stream()
    stream.close()
    pa.terminate()
    print("[LOCAL-SPK] 喇叭已停止", flush=True)


def play_pcm_locally(pcm16: bytes):
    """由 audio_stream.py 呼叫，將 PCM 資料送入本機喇叭播放佇列。"""
    if _stop_event.is_set():
        return
    try:
        _speaker_queue.put_nowait(pcm16)
    except queue.Full:
        # 佇列滿時丟棄最舊的一包，保持即時性
        try:
            _speaker_queue.get_nowait()
            _speaker_queue.put_nowait(pcm16)
        except Exception:
            pass


# ── 啟動 / 停止 ──────────────────────────────────────────────────────────────

def start():
    """啟動所有本機裝置執行緒（攝影機、麥克風、喇叭）。"""
    if not LOCAL_MODE:
        return
    global _speaker_thread
    _stop_event.clear()
    threading.Thread(target=_webcam_loop,  daemon=True, name="local-cam").start()
    threading.Thread(target=_mic_loop,     daemon=True, name="local-mic").start()
    _speaker_thread = threading.Thread(target=_speaker_loop, daemon=True, name="local-spk")
    _speaker_thread.start()
    print("[LOCAL] 本機裝置模式已啟動（攝影機 + 麥克風 + 喇叭）", flush=True)


def stop():
    """停止所有本機裝置執行緒。"""
    _stop_event.set()
    _speaker_queue.put_nowait(None)   # 喚醒喇叭執行緒讓它退出
