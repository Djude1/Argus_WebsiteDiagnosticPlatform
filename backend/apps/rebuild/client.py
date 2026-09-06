"""OpenCode agent server 的最小 HTTP client。

只實作本功能真正用到的四個端點（皆已對 1.18.29 實測）：

    POST /session?directory=<dir>          建立 session，directory 決定 agent 的 cwd
    POST /session/<id>/message             送 prompt，同步阻塞到 agent 回完
    GET  /file/content?path=&directory=    把 agent 寫出的檔案讀回來
    POST /session/<id>/abort               逾時後收尾，避免留下跑不停的 session

**為什麼要靠 /file/content 而不是直接讀回應文字**：opencode server 跑在
另一台主機上，跟 worker pod 沒有共用檔案系統。agent 產出的網頁動輒上百 KB，
硬要它一次吐在回應裡會撞到模型的單則輸出上限；讓它寫檔、我們再讀回來，
agent 就能分多次編輯把檔案寫完。
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class OpenCodeError(Exception):
    """可以直接顯示給使用者的 OpenCode 失敗原因。

    與 requests.RequestException（連不上／逾時）分開：agent 端 provider 設定
    壞掉和網路不通，處理方式完全不同，混在一起會讓維運誤判。
    """


def _public_error(payload: Any) -> str:
    """把 opencode 的 {name, data:{message}} 壓成一行可公開的訊息。

    只取 name 與 message 前 200 字：回應裡可能夾帶被掃描站的內容或路徑，
    整包塞進 DB 的 error 欄位會把不該外流的東西帶到前端。
    """
    if isinstance(payload, dict):
        name = payload.get("name", "Error")
        message = (payload.get("data") or {}).get("message") or ""
        return f"{name}: {message[:200]}" if message else str(name)
    return str(payload)[:200]


class OpenCodeClient:
    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.base_url = (
            base_url if base_url is not None else settings.ARGUS_OPENCODE_BASE_URL
        ).rstrip("/")
        user = username if username is not None else settings.ARGUS_OPENCODE_USERNAME
        pwd = password if password is not None else settings.ARGUS_OPENCODE_PASSWORD
        self.auth = (user, pwd) if user or pwd else None
        self.timeout = timeout or settings.ARGUS_OPENCODE_TIMEOUT

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = requests.request(
            method,
            f"{self.base_url}{path}",
            auth=self.auth,
            timeout=kwargs.pop("timeout", self.timeout),
            **kwargs,
        )
        if response.status_code == 401:
            raise OpenCodeError(
                "OpenCode 認證失敗（401）：ARGUS_OPENCODE_USERNAME / PASSWORD "
                "與 server 端的 OPENCODE_SERVER_USERNAME / PASSWORD 不一致"
            )
        if response.status_code >= 400:
            try:
                payload = response.json()
            except ValueError:
                raise OpenCodeError(
                    f"OpenCode 回應 HTTP {response.status_code}"
                ) from None
            raise OpenCodeError(_public_error(payload))
        return response.json()

    def create_session(self, directory: str) -> str:
        """建立 session。

        directory 一定要傳：不傳的話 agent 的 cwd 會落在 server 的家目錄，
        不同掃描的產出會互相覆蓋，而且把 agent 放在它自己的設定檔旁邊工作。
        """
        data = self._request(
            "POST", "/session", params={"directory": directory}, json={}
        )
        session_id = data.get("id")
        if not session_id:
            raise OpenCodeError("OpenCode 未回傳 session id")
        return session_id

    def prompt(self, session_id: str, text: str, agent: str, model: str = "") -> dict:
        """送出 prompt 並阻塞到 agent 回完，回傳 {text, cost, model_id}。"""
        body: dict[str, Any] = {
            "agent": agent,
            "parts": [{"type": "text", "text": text}],
        }
        if model:
            provider_id, _, model_id = model.partition("/")
            if not model_id:
                raise OpenCodeError(
                    f"ARGUS_OPENCODE_MODEL 格式應為 provider/model，收到 {model!r}"
                )
            body["model"] = {"providerID": provider_id, "modelID": model_id}

        data = self._request("POST", f"/session/{session_id}/message", json=body)
        info = data.get("info") or {}
        if info.get("error"):
            raise OpenCodeError(_public_error(info["error"]))
        texts = [
            part.get("text", "")
            for part in data.get("parts") or []
            if part.get("type") == "text"
        ]
        return {
            "text": "\n".join(t for t in texts if t),
            "cost": info.get("cost") or 0,
            "model_id": info.get("modelID") or "",
        }

    def read_file(self, directory: str, path: str) -> str | None:
        """讀 agent 寫出的檔案；不存在回 None（讓呼叫端走 fallback）。"""
        try:
            data = self._request(
                "GET",
                "/file/content",
                params={"path": path, "directory": directory},
                timeout=60,
            )
        except OpenCodeError:
            return None
        content = data.get("content")
        return content if content else None

    def abort(self, session_id: str) -> None:
        """盡力而為地中止；失敗不拋——這是收尾動作，不該蓋掉真正的錯誤。"""
        try:
            self._request("POST", f"/session/{session_id}/abort", json={}, timeout=15)
        except (OpenCodeError, requests.RequestException):
            logger.warning("OpenCode session %s abort 失敗", session_id)
