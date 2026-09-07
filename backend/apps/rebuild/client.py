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

import json
import logging
import time
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# SSE socket 上多久沒有任何位元組就放棄。給得寬鬆，因為推理型模型在兩個
# delta 之間可以想很久。
_STREAM_READ_TIMEOUT = 180

# 描述一次工具呼叫時，最能說明「它在對什麼動作」的參數
_TOOL_DETAIL_KEYS = ("filePath", "path", "command", "pattern", "query", "url")


def _tool_detail(payload: Any, limit: int = 120) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in _TOOL_DETAIL_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:limit]
    return ""


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
        # prompt_async / abort 回 204 無內容，硬要 .json() 會炸。
        if not response.content:
            return None
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

    def _message_body(self, text: str, agent: str, model: str) -> dict[str, Any]:
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
        return body

    def session_result(self, session_id: str) -> dict:
        """整個 session 跑完後的總結：回覆文字、**總花費**、模型。

        一次執行會產生多則 assistant 訊息（每個 step 一則），花費各自分開記。
        只看最後一則會漏算前面所有 step——實測一次三步的執行，最後一則只佔
        總花費的 16%。計費是照 cost 算的，所以這裡必須加總。
        """
        data = self._request("GET", f"/session/{session_id}/message", timeout=60)
        rows = data if isinstance(data, list) else []
        total_cost = 0.0
        text = ""
        model_id = ""
        for row in rows:
            info = row.get("info") or {}
            if info.get("role") != "assistant":
                continue
            if info.get("error"):
                raise OpenCodeError(_public_error(info["error"]))
            total_cost += info.get("cost") or 0
            model_id = info.get("modelID") or model_id
            texts = [
                p.get("text", "")
                for p in row.get("parts") or []
                if p.get("type") == "text" and p.get("text")
            ]
            if texts:
                # 取最後一則有內容的，那是 agent 的收尾摘要
                text = "\n".join(texts)
        if not model_id:
            raise OpenCodeError("agent 沒有回覆")
        return {"text": text, "cost": total_cost, "model_id": model_id}

    def prompt(self, session_id: str, text: str, agent: str, model: str = "") -> dict:
        """送出 prompt 並阻塞到 agent 回完，回傳 {text, cost, model_id}。"""
        body = self._message_body(text, agent, model)
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

    def prompt_async(self, session_id: str, text: str, agent: str, model: str = "") -> None:
        """送出 prompt 後立刻返回（204），實際進度從 /event 串流取得。"""
        self._request(
            "POST",
            f"/session/{session_id}/prompt_async",
            json=self._message_body(text, agent, model),
            timeout=30,
        )

    def stream(
        self, session_id: str, text: str, agent: str, model: str = "", directory: str = ""
    ):
        """送出 prompt 並逐步吐出 agent 的進度事件。

        產出的事件型別：
          thinking — {"text"}：模型的推理過程
          text     — {"text"}：回覆內容
          tool     — {"name", "detail"}：它實際動用了哪個工具、對象是什麼
          done / error

        **SSE 必須在送出 prompt 之前訂閱**：反過來會有競態，開頭幾個 delta
        會直接遺失，畫面上看起來像 agent 前幾秒什麼都沒做。
        """
        params = {"directory": directory} if directory else {}
        events = requests.get(
            f"{self.base_url}/event",
            auth=self.auth,
            params=params,
            stream=True,
            timeout=(10, _STREAM_READ_TIMEOUT),
        )
        try:
            events.raise_for_status()
            # text/event-stream 不帶 charset，requests 會退回 ISO-8859-1，
            # 中文推理過程會整段變成亂碼。串流本身是 UTF-8，明講。
            events.encoding = "utf-8"
            self.prompt_async(session_id, text, agent, model)
            yield from self._consume_events(events, session_id)
        finally:
            events.close()

    def _consume_events(self, events, session_id: str):
        deadline = time.monotonic() + self.timeout
        part_kind: dict[str, str] = {}   # partID -> text | reasoning
        user_messages: set[str] = set()  # 使用者自己的 prompt 會被回放，要濾掉

        for raw in events.iter_lines(decode_unicode=True):
            if time.monotonic() > deadline:
                yield {"type": "error", "text": f"超過 {self.timeout} 秒未結束"}
                return
            if not raw or not raw.startswith("data:"):
                continue  # SSE keep-alive 與用不到的欄位行
            try:
                event = json.loads(raw[5:].strip())
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            props = event.get("properties") or {}
            if props.get("sessionID") != session_id:
                continue  # /event 是全 server 共用的，別的 session 也會經過

            etype = event.get("type") or ""
            if etype == "message.updated":
                info = props.get("info") or {}
                if info.get("role") == "user":
                    user_messages.add(info.get("id"))
                elif info.get("time", {}).get("completed"):
                    yield {"type": "done"}
                    return
            elif etype == "message.part.updated":
                part = props.get("part") or {}
                if part.get("messageID") in user_messages:
                    continue
                kind = part.get("type")
                if kind in ("text", "reasoning"):
                    part_kind[part.get("id")] = kind
                elif kind == "tool":
                    state = (part.get("state") or {}).get("status")
                    if state == "running":
                        yield {
                            "type": "tool",
                            "name": part.get("tool") or "",
                            "detail": _tool_detail((part.get("state") or {}).get("input")),
                        }
            elif etype == "message.part.delta":
                kind = part_kind.get(props.get("partID"))
                if kind:
                    yield {
                        "type": "thinking" if kind == "reasoning" else "text",
                        "text": props.get("delta", ""),
                    }
            # 新版 server 用的 session.next.* 家族
            elif etype == "session.next.reasoning.delta":
                yield {"type": "thinking", "text": props.get("delta", "")}
            elif etype == "session.next.text.delta":
                yield {"type": "text", "text": props.get("delta", "")}
            elif etype == "session.next.tool.called":
                yield {"type": "tool", "name": props.get("tool", ""), "detail": ""}

        yield {"type": "error", "text": "事件串流中斷（agent server 可能已停止）"}

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

    def find_file(self, directory: str, filename: str) -> str | None:
        """在工作目錄下找出這個檔名的實際位置。

        存在的理由：agent 不見得會照指示寫在 cwd——實測它曾自己建了子目錄再把
        檔案放進去，回覆裡還講得很篤定。與其相信它，不如問 server 檔案在哪。
        只接受 basename 完全相同的結果，避免拿到名字相近的別的檔。
        """
        try:
            paths = self._request(
                "GET",
                "/find/file",
                params={"query": filename, "directory": directory},
                timeout=60,
            )
        except OpenCodeError:
            return None
        if not isinstance(paths, list):
            return None
        for path in paths:
            if isinstance(path, str) and path.rsplit("/", 1)[-1] == filename:
                return path
        return None

    def abort(self, session_id: str) -> None:
        """盡力而為地中止；失敗不拋——這是收尾動作，不該蓋掉真正的錯誤。"""
        try:
            self._request("POST", f"/session/{session_id}/abort", json={}, timeout=15)
        except (OpenCodeError, requests.RequestException):
            logger.warning("OpenCode session %s abort 失敗", session_id)
