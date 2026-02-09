# bridge_io.py
# Thread-safe frame buffer: capture thread pushes JPEG → inference thread pulls BGR
# Adapted from OpenAIglasses_for_Navigation/bridge_io.py

import threading
from collections import deque
import time
import cv2
import numpy as np

# Raw JPEG frame buffer (keep only the latest N frames)
_MAX_BUF = 4
_frames = deque(maxlen=_MAX_BUF)
_cond = threading.Condition()

# Sender callback for broadcasting annotated JPEG to frontend viewers
_sender_lock = threading.Lock()
_sender_cb = None

# Detection result callback for publishing structured results
_det_sender_lock = threading.Lock()
_det_sender_cb = None


def set_sender(cb):
    """Register a callback: cb(jpeg_bytes) -> None, called by app_main.py at startup."""
    global _sender_cb
    with _sender_lock:
        _sender_cb = cb


def set_detection_sender(cb):
    """Register a callback: cb(detection_dict) -> None, for publishing detection results."""
    global _det_sender_cb
    with _det_sender_lock:
        _det_sender_cb = cb


def push_raw_jpeg(jpeg_bytes: bytes):
    """Called by frame_capture thread when a new JPEG frame arrives from ESP32."""
    if not jpeg_bytes:
        return
    with _cond:
        _frames.append((time.time(), jpeg_bytes))
        _cond.notify_all()


def wait_raw_bgr(timeout_sec: float = 0.5):
    """Called by inference thread: wait for and return the latest BGR frame. Returns None on timeout."""
    t_end = time.time() + timeout_sec
    last = None
    while time.time() < t_end:
        with _cond:
            if _frames:
                last = _frames[-1]
        if last is None:
            time.sleep(0.01)
            continue
        # Decode JPEG to BGR
        ts, jpeg = last
        arr = np.frombuffer(jpeg, dtype=np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if bgr is not None:
            return bgr
        # Decode failed, wait and retry
        time.sleep(0.01)
    return None


def send_vis_bgr(bgr, quality: int = 80):
    """Called by inference thread: push annotated frame to frontend viewers."""
    if bgr is None:
        return
    ok, enc = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        return
    with _sender_lock:
        cb = _sender_cb
    if cb:
        try:
            cb(enc.tobytes())
        except Exception:
            pass


def send_detections(detection_dict: dict):
    """Called by inference thread: publish structured detection results."""
    with _det_sender_lock:
        cb = _det_sender_cb
    if cb:
        try:
            cb(detection_dict)
        except Exception:
            pass
