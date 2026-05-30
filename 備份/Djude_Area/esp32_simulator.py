# esp32_simulator.py
# -*- coding: utf-8 -*-
"""
ESP32 模擬器：以電腦裝置取代 ESP32 硬體連接 app_main.py。

啟動方式（先啟動主伺服器，再開另一個終端機執行此腳本）：
    uv run esp32_simulator.py

模擬的三個連接：
  1. /ws/camera  → 電腦攝影機 JPEG 影像
  2. /ws_audio   → 電腦麥克風 PCM16 音訊（上行）
  3. /stream.wav → 電腦喇叭播放（下行）
"""

import asyncio
import threading
import time
import http.client
import os
import sys

import cv2
import pyaudio
import websockets

# ── 設定 ────────────────────────────────────────────────────────────────────
SERVER_HOST    = os.getenv("SERVER_HOST_SIM", "127.0.0.1")
SERVER_PORT    = int(os.getenv("SERVER_PORT",  "8081"))
CAM_INDEX      = int(os.getenv("CAM_INDEX",    "0"))
JPEG_QUALITY   = int(os.getenv("LOCAL_CAM_QUALITY", "70"))
CAM_FPS        = int(os.getenv("LOCAL_CAM_FPS", "10"))
SAMPLE_RATE    = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
CHUNK_MS       = int(os.getenv("AUDIO_CHUNK_MS", "20"))
STREAM_SR      = 8000   # 下行音訊取樣率（與 audio_stream.py 一致）

WS_CAMERA = f"ws://{SERVER_HOST}:{SERVER_PORT}/ws/camera"
WS_AUDIO  = f"ws://{SERVER_HOST}:{SERVER_PORT}/ws_audio"
STREAM_URL = f"/stream.wav"

_stop = threading.Event()


# ── 1. 攝影機上行 ────────────────────────────────────────────────────────────

async def camera_loop():
    delay = 1.0 / CAM_FPS
    cap = cv2.VideoCapture(CAM_INDEX)
    if not cap.isOpened():
        print(f"[SIM-CAM] 無法開啟攝影機 index={CAM_INDEX}", flush=True)
        return

    print(f"[SIM-CAM] 攝影機已開啟（index={CAM_INDEX}, {CAM_FPS}fps）", flush=True)

    while not _stop.is_set():
        try:
            async with websockets.connect(WS_CAMERA, ping_interval=20) as ws:
                print("[SIM-CAM] 已連線至 /ws/camera", flush=True)

                # 接收伺服器控制指令（SET:QUALITY / SET:FPS 等，忽略即可）
                async def _recv():
                    try:
                        async for msg in ws:
                            print(f"[SIM-CAM] 伺服器指令: {msg}", flush=True)
                    except Exception:
                        pass
                asyncio.create_task(_recv())

                while not _stop.is_set() and ws.open:
                    t0 = time.monotonic()
                    ret, frame = cap.read()
                    if ret:
                        ok, jpg = cv2.imencode(
                            ".jpg", frame,
                            [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
                        )
                        if ok:
                            await ws.send(jpg.tobytes())
                    elapsed = time.monotonic() - t0
                    await asyncio.sleep(max(0.0, delay - elapsed))

        except Exception as e:
            if not _stop.is_set():
                print(f"[SIM-CAM] 連線中斷，3 秒後重試：{e}", flush=True)
                await asyncio.sleep(3)

    cap.release()
    print("[SIM-CAM] 攝影機已停止", flush=True)


# ── 2. 麥克風上行 ────────────────────────────────────────────────────────────

async def audio_upload_loop():
    chunk_frames = SAMPLE_RATE * CHUNK_MS // 1000   # 320 samples

    while not _stop.is_set():
        try:
            async with websockets.connect(WS_AUDIO, ping_interval=20) as ws:
                print("[SIM-MIC] 已連線至 /ws_audio", flush=True)

                # 送出 START，等待 OK:STARTED
                await ws.send("START")
                try:
                    resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    print(f"[SIM-MIC] 伺服器回應: {resp}", flush=True)
                except asyncio.TimeoutError:
                    print("[SIM-MIC] 等待 OK:STARTED 逾時", flush=True)

                # 開啟麥克風串流
                pa = pyaudio.PyAudio()
                mic_stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=SAMPLE_RATE,
                    input=True,
                    frames_per_buffer=chunk_frames,
                )
                print("[SIM-MIC] 麥克風已啟動，開始收音", flush=True)

                loop = asyncio.get_running_loop()

                def _mic_reader():
                    """從麥克風持續讀取並送到 WebSocket。"""
                    while not _stop.is_set() and ws.open:
                        try:
                            data = mic_stream.read(
                                chunk_frames, exception_on_overflow=False
                            )
                            asyncio.run_coroutine_threadsafe(ws.send(data), loop)
                        except Exception as e:
                            print(f"[SIM-MIC] 讀取錯誤: {e}", flush=True)
                            break

                mic_thread = threading.Thread(
                    target=_mic_reader, daemon=True, name="sim-mic"
                )
                mic_thread.start()

                # 監聽伺服器是否要求 RESTART
                try:
                    async for msg in ws:
                        if isinstance(msg, str) and "RESTART" in msg:
                            print("[SIM-MIC] 收到 RESTART，重新連線", flush=True)
                            break
                except Exception:
                    pass
                finally:
                    mic_stream.stop_stream()
                    mic_stream.close()
                    pa.terminate()

        except Exception as e:
            if not _stop.is_set():
                print(f"[SIM-MIC] 連線中斷，3 秒後重試：{e}", flush=True)
                await asyncio.sleep(3)

    print("[SIM-MIC] 麥克風已停止", flush=True)


# ── 3. 喇叭下行（HTTP 串流）─────────────────────────────────────────────────

def audio_download_loop():
    """從 /stream.wav 讀取音訊並用本機喇叭播放（執行在背景執行緒）。"""
    pa = pyaudio.PyAudio()
    spk_stream = pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=STREAM_SR,
        output=True,
        frames_per_buffer=STREAM_SR * CHUNK_MS // 1000,
    )
    print(f"[SIM-SPK] 本機喇叭已啟動（{STREAM_SR} Hz）", flush=True)

    while not _stop.is_set():
        try:
            conn = http.client.HTTPConnection(f"{SERVER_HOST}:{SERVER_PORT}", timeout=None)
            conn.request("GET", STREAM_URL)
            resp = conn.getresponse()

            if resp.status != 200:
                print(f"[SIM-SPK] /stream.wav 回應 {resp.status}，3 秒後重試", flush=True)
                time.sleep(3)
                continue

            # 跳過 WAV 檔頭（44 bytes）
            resp.read(44)
            print("[SIM-SPK] 已連線至 /stream.wav，開始播放", flush=True)

            chunk_bytes = STREAM_SR * CHUNK_MS // 1000 * 2  # 20ms PCM16
            while not _stop.is_set():
                chunk = resp.read(chunk_bytes)
                if not chunk:
                    break
                spk_stream.write(chunk)

        except Exception as e:
            if not _stop.is_set():
                print(f"[SIM-SPK] 連線中斷，3 秒後重試：{e}", flush=True)
                time.sleep(3)

    spk_stream.stop_stream()
    spk_stream.close()
    pa.terminate()
    print("[SIM-SPK] 喇叭已停止", flush=True)


# ── 主程式 ───────────────────────────────────────────────────────────────────

async def main():
    print(
        f"[SIM] ESP32 模擬器啟動\n"
        f"      伺服器: {SERVER_HOST}:{SERVER_PORT}\n"
        f"      攝影機: index={CAM_INDEX}, {CAM_FPS}fps\n"
        f"      麥克風: {SAMPLE_RATE}Hz, {CHUNK_MS}ms chunk\n"
        f"      喇叭:   {STREAM_SR}Hz\n"
        f"      按 Ctrl+C 停止",
        flush=True,
    )

    # 喇叭下行放在背景執行緒（HTTP 阻塞式讀取）
    threading.Thread(
        target=audio_download_loop, daemon=True, name="sim-spk"
    ).start()

    # 攝影機 + 麥克風並行跑
    try:
        await asyncio.gather(camera_loop(), audio_upload_loop())
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _stop.set()
        print("\n[SIM] 已停止", flush=True)
