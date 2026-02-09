# dify_client.py
# Dify Workflow API integration (Phase 2)

import time
import json
import base64
import httpx
from models import DetectionResult, DifyResponse


class DifyThrottler:
    """Rate-limits Dify API calls to avoid overwhelming the service."""

    def __init__(self, min_interval: float = 2.0):
        self.min_interval = min_interval
        self._last_call = 0.0
        self._last_hash = None

    def should_call(self, detections: DetectionResult) -> bool:
        now = time.time()
        if now - self._last_call < self.min_interval:
            return False
        # Check if detections changed significantly
        det_hash = self._hash(detections)
        if det_hash == self._last_hash:
            return False
        return True

    def mark_called(self, detections: DetectionResult):
        self._last_call = time.time()
        self._last_hash = self._hash(detections)

    @staticmethod
    def _hash(detections: DetectionResult) -> str:
        classes = sorted([d.class_name for d in detections.detections])
        return "|".join(classes)


class DifyClient:
    """Async client for Dify Workflow API."""

    def __init__(self, base_url: str, api_key: str, workflow_id: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.workflow_id = workflow_id
        self._client = httpx.AsyncClient(timeout=30.0)

    async def run_workflow(
        self,
        detections: DetectionResult,
        image_b64: str = None,
    ) -> DifyResponse:
        """Send detection results to Dify workflow and return the response."""
        # Format detection data for Dify input
        det_summary = []
        for d in detections.detections:
            det_summary.append({
                "object": d.class_name,
                "confidence": d.confidence,
                "position_x": d.center_x,
                "position_y": d.center_y,
                "size": d.area_ratio,
            })

        inputs = {
            "detections": json.dumps(det_summary, ensure_ascii=False),
            "object_count": str(detections.count),
            "timestamp": str(detections.timestamp),
        }
        if image_b64:
            inputs["image"] = image_b64

        payload = {
            "inputs": inputs,
            "response_mode": "blocking",
            "user": "esp32_device",
        }

        try:
            resp = await self._client.post(
                f"{self.base_url}/workflows/run",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

            return DifyResponse(
                text=data.get("data", {}).get("outputs", {}).get("text", ""),
                workflow_run_id=data.get("workflow_run_id", ""),
                status=data.get("data", {}).get("status", ""),
            )
        except Exception as e:
            print(f"[DifyClient] Error: {e}")
            return DifyResponse(text="", status="error")

    async def close(self):
        await self._client.aclose()
