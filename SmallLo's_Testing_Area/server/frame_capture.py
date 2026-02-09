# frame_capture.py
# Background thread that pulls MJPEG frames from ESP32 HTTP stream
# Based on Hardware/34/CameraWebServer_34/Yolo_Server/main.py

import threading
import time
import cv2
import numpy as np
import bridge_io


class FrameCapture:
    """Captures MJPEG stream from ESP32 in a background thread."""

    def __init__(self, stream_url: str):
        self.stream_url = stream_url
        self._thread = None
        self._running = False
        self._cap = None
        self._fps = 0.0
        self._frame_count = 0
        self._last_fps_time = time.time()

    def start(self):
        """Start the capture background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        print(f"[FrameCapture] Started capturing from {self.stream_url}")

    def stop(self):
        """Stop the capture thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        if self._cap:
            self._cap.release()
            self._cap = None
        print("[FrameCapture] Stopped")

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def is_running(self) -> bool:
        return self._running

    def _capture_loop(self):
        """Main capture loop running in background thread."""
        while self._running:
            # Open stream if not connected
            if self._cap is None or not self._cap.isOpened():
                print(f"[FrameCapture] Connecting to {self.stream_url}...")
                self._cap = cv2.VideoCapture(self.stream_url)
                if not self._cap.isOpened():
                    print("[FrameCapture] Failed to connect, retrying in 2s...")
                    time.sleep(2.0)
                    continue
                print("[FrameCapture] Connected successfully")

            # Read frame
            ret, frame = self._cap.read()
            if not ret:
                print("[FrameCapture] Frame read failed, reconnecting...")
                self._cap.release()
                self._cap = None
                time.sleep(1.0)
                continue

            # Encode frame to JPEG and push to bridge
            ok, jpeg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if ok:
                bridge_io.push_raw_jpeg(jpeg.tobytes())

            # Update FPS counter
            self._frame_count += 1
            now = time.time()
            elapsed = now - self._last_fps_time
            if elapsed >= 1.0:
                self._fps = self._frame_count / elapsed
                self._frame_count = 0
                self._last_fps_time = now

        # Cleanup
        if self._cap:
            self._cap.release()
            self._cap = None
