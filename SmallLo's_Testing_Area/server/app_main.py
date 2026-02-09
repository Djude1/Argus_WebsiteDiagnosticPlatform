# app_main.py
# FastAPI server for ESP32 + YOLO + Dify pipeline

import sys
import asyncio
import threading
import time
import json

# Windows asyncio compatibility
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pathlib import Path

import config
import bridge_io
from frame_capture import FrameCapture
from yolo_detector import YOLODetector

# ─── FastAPI App ───
app = FastAPI(title="SmallLo YOLO Server")

# Mount static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# ─── Global State ───
viewer_clients: set = set()        # WebSocket clients receiving annotated frames
detection_clients: set = set()     # WebSocket clients receiving detection JSON
frame_capture: FrameCapture = None
yolo_detector: YOLODetector = None
inference_thread: threading.Thread = None
_running = False
_latest_detections: dict = {}      # Most recent detection result
_main_loop: asyncio.AbstractEventLoop = None


# ─── Inference Loop (Background Thread) ───
def _inference_loop():
    """Continuously pull frames, run YOLO, annotate, and broadcast."""
    global _latest_detections
    print("[Inference] Loop started")

    while _running:
        bgr = bridge_io.wait_raw_bgr(timeout_sec=0.5)
        if bgr is None:
            continue

        # Run YOLO detection
        result = yolo_detector.detect(bgr)

        # Annotate frame
        annotated = yolo_detector.annotate(bgr, result)

        # Send annotated frame to viewers
        bridge_io.send_vis_bgr(annotated)

        # Publish detection results
        det_dict = result.to_dict()
        _latest_detections = det_dict
        bridge_io.send_detections(det_dict)

    print("[Inference] Loop stopped")


# ─── WebSocket Broadcast Callbacks ───
def _broadcast_jpeg(jpeg_bytes: bytes):
    """Send annotated JPEG to all viewer WebSocket clients."""
    if not viewer_clients or _main_loop is None:
        return

    async def _send():
        dead = set()
        for ws in list(viewer_clients):
            try:
                await ws.send_bytes(jpeg_bytes)
            except Exception:
                dead.add(ws)
        viewer_clients.difference_update(dead)

    asyncio.run_coroutine_threadsafe(_send(), _main_loop)


def _broadcast_detections(det_dict: dict):
    """Send detection results JSON to all detection WebSocket clients."""
    if not detection_clients or _main_loop is None:
        return

    async def _send():
        dead = set()
        text = json.dumps(det_dict, ensure_ascii=False)
        for ws in list(detection_clients):
            try:
                await ws.send_text(text)
            except Exception:
                dead.add(ws)
        detection_clients.difference_update(dead)

    asyncio.run_coroutine_threadsafe(_send(), _main_loop)


# ─── Lifecycle Events ───
@app.on_event("startup")
async def on_startup():
    global frame_capture, yolo_detector, inference_thread, _running, _main_loop

    _main_loop = asyncio.get_event_loop()

    # Load YOLO model
    print("=" * 50)
    print("[Startup] Loading YOLO model...")
    yolo_detector = YOLODetector(
        model_path=config.YOLO_MODEL_PATH,
        confidence=config.YOLO_CONFIDENCE,
    )

    # Register broadcast callbacks
    bridge_io.set_sender(_broadcast_jpeg)
    bridge_io.set_detection_sender(_broadcast_detections)

    # Start frame capture from ESP32
    print(f"[Startup] Starting frame capture from {config.ESP32_STREAM_URL}")
    frame_capture = FrameCapture(config.ESP32_STREAM_URL)
    frame_capture.start()

    # Start inference thread
    _running = True
    inference_thread = threading.Thread(target=_inference_loop, daemon=True)
    inference_thread.start()

    print("[Startup] Server ready!")
    print(f"[Startup] Dashboard: http://localhost:{config.SERVER_PORT}")
    print("=" * 50)


@app.on_event("shutdown")
async def on_shutdown():
    global _running
    _running = False

    if frame_capture:
        frame_capture.stop()
    if inference_thread:
        inference_thread.join(timeout=3.0)

    print("[Shutdown] Server stopped")


# ─── HTTP Endpoints ───
@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the monitoring dashboard."""
    html_path = static_dir / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "capture_fps": round(frame_capture.fps, 1) if frame_capture else 0,
        "capture_running": frame_capture.is_running if frame_capture else False,
    }


@app.get("/api/detections")
async def get_detections():
    """Get the latest detection results."""
    return JSONResponse(content=_latest_detections)


# ─── WebSocket Endpoints ───
@app.websocket("/ws/viewer")
async def ws_viewer(ws: WebSocket):
    """Browser connects here to receive annotated JPEG frames."""
    await ws.accept()
    viewer_clients.add(ws)
    print(f"[Viewer] Connected ({len(viewer_clients)} total)")
    try:
        while True:
            # Keep connection alive, receive pings
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        viewer_clients.discard(ws)
        print(f"[Viewer] Disconnected ({len(viewer_clients)} total)")


@app.websocket("/ws/detections")
async def ws_detections(ws: WebSocket):
    """Browser connects here to receive real-time detection results as JSON."""
    await ws.accept()
    detection_clients.add(ws)
    print(f"[Detections] Connected ({len(detection_clients)} total)")
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        detection_clients.discard(ws)
        print(f"[Detections] Disconnected ({len(detection_clients)} total)")


# ─── Entry Point ───
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app_main:app",
        host=config.SERVER_HOST,
        port=config.SERVER_PORT,
        workers=1,
        loop="asyncio",
    )
