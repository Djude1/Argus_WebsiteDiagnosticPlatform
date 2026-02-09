import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from server directory
_env_path = Path(__file__).parent / ".env"
load_dotenv(_env_path)

# ESP32 Camera
ESP32_STREAM_URL = os.getenv("ESP32_STREAM_URL", "http://192.168.137.189:81/stream")

# YOLO Model
YOLO_MODEL_PATH = os.getenv("YOLO_MODEL_PATH", "../../YOLO_Module/YOLO_Traine_Model/yolo11n.pt")
YOLO_CONFIDENCE = float(os.getenv("YOLO_CONFIDENCE", "0.25"))

# Server
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8081"))

# Dify (Phase 2)
DIFY_API_URL = os.getenv("DIFY_API_URL", "http://localhost/v1")
DIFY_API_KEY = os.getenv("DIFY_API_KEY", "")
DIFY_WORKFLOW_ID = os.getenv("DIFY_WORKFLOW_ID", "")
DIFY_CALL_INTERVAL = float(os.getenv("DIFY_CALL_INTERVAL", "2.0"))
