"""LLM provider 抽象與 OpenAI-compatible 實作。

設計原則：
- 對外只暴露 ChatProvider 介面與 ProviderChain；上層 Agent 不應該知道是哪家。
- MiniMax / GLM 都採 OpenAI-compatible 端點，messages/tools/tool_calls 結構一致。
- Gemini 留 chat() 純文字介面，作為 fallback 文字分析或備援；不在本期接 tool calling。
- 任何錯誤都 raise ProviderError，並附公開等級資訊（provider、HTTP、模型、訊息片段）；
  不把 raw response body 或 key 帶出來。
- 嚴禁在 log/exception/repr 中印出 API key。
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import requests

DEFAULT_TIMEOUT = 60


@dataclass
class ToolCall:
    """單一 tool call 的標準化表示。"""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResponse:
    """provider chat 回應的標準化表示。"""

    provider: str
    model: str
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str = ""
    raw_choice: dict[str, Any] = field(default_factory=dict)


class ProviderError(Exception):
    """provider 呼叫失敗。message 只含可公開資訊。"""

    def __init__(self, provider: str, http_status: int | str, hint: str = ""):
        self.provider = provider
        self.http_status = http_status
        self.hint = hint
        super().__init__(f"{provider} failed http={http_status} {hint}".strip())


class ChatProvider:
    """所有 provider 必須實作的介面。"""

    name: str = "base"
    default_model: str = ""
    supports_tools: bool = False

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> ChatResponse:
        raise NotImplementedError


def _parse_openai_choice(provider: str, model: str, payload: dict[str, Any]) -> ChatResponse:
    """從 OpenAI-compatible 回應抽出 ChatResponse。"""
    try:
        choice = payload["choices"][0]
        message = choice.get("message", {}) or {}
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(provider, "200", f"missing choices: {exc.__class__.__name__}") from exc

    tool_calls: list[ToolCall] = []
    for raw in message.get("tool_calls") or []:
        fn = (raw or {}).get("function", {}) or {}
        args_str = fn.get("arguments", "") or ""
        try:
            args = json.loads(args_str) if args_str else {}
        except json.JSONDecodeError:
            args = {"_raw": args_str}
        tool_calls.append(
            ToolCall(
                id=raw.get("id", ""),
                name=fn.get("name", ""),
                arguments=args if isinstance(args, dict) else {"_raw": args},
            )
        )

    usage = payload.get("usage", {}) or {}
    return ChatResponse(
        provider=provider,
        model=model,
        content=message.get("content") or "",
        tool_calls=tool_calls,
        prompt_tokens=usage.get("prompt_tokens", 0) or 0,
        completion_tokens=usage.get("completion_tokens", 0) or 0,
        total_tokens=usage.get("total_tokens", 0) or 0,
        finish_reason=choice.get("finish_reason", "") or "",
        raw_choice=message,
    )


class _OpenAICompatibleProvider(ChatProvider):
    """OpenAI Chat Completions 相容 provider 的共用實作。"""

    base_url: str = ""
    api_key_env: str = ""

    supports_tools = True

    def __init__(self) -> None:
        self._key = os.environ.get(self.api_key_env, "").strip()
        # 不在這裡 raise；讓 caller 可以透過 ProviderChain 跳過未設定的 provider。

    @property
    def available(self) -> bool:
        return bool(self._key)

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> ChatResponse:
        if not self.available:
            raise ProviderError(self.name, "no_key", f"{self.api_key_env} not set")

        body: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = tool_choice

        try:
            r = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(body),
                timeout=DEFAULT_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise ProviderError(self.name, "network", exc.__class__.__name__) from exc

        if r.status_code != 200:
            # 不輸出 raw body，可能含 prompt 或敏感訊息
            raise ProviderError(self.name, r.status_code, "non-200")

        try:
            data = r.json()
        except ValueError as exc:
            raise ProviderError(self.name, "200", "invalid_json") from exc

        return _parse_openai_choice(self.name, body["model"], data)


class MiniMaxProvider(_OpenAICompatibleProvider):
    name = "minimax"
    default_model = "MiniMax-M2.7"
    api_key_env = "MINIMAX_API_KEY"
    base_url = os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.io/v1").rstrip("/")


class GLMProvider(_OpenAICompatibleProvider):
    name = "glm"
    default_model = "glm-4.5-flash"
    api_key_env = "GLM_API_KEY"
    base_url = os.environ.get(
        "GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"
    ).rstrip("/")


class GeminiProvider(ChatProvider):
    """Gemini 文字分析備援。Phase 2 主迴圈不走這條，但保留 chat() 介面。"""

    name = "gemini"
    default_model = "gemini-2.5-flash"
    api_key_env = "GOOGLE_API_KEY"
    supports_tools = False

    def __init__(self) -> None:
        self._key = os.environ.get(self.api_key_env, "").strip()
        self.base_url = os.environ.get(
            "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
        ).rstrip("/")

    @property
    def available(self) -> bool:
        return bool(self._key)

    def chat_with_tools(self, *args: Any, **kwargs: Any) -> ChatResponse:
        raise ProviderError(self.name, "unsupported", "Gemini tool-calling 未在本期接入")

    def chat_text(self, prompt: str, model: str | None = None) -> ChatResponse:
        """純文字分析。不接 tool calling，僅供報告解釋或備援。"""
        if not self.available:
            raise ProviderError(self.name, "no_key", f"{self.api_key_env} not set")

        model = model or self.default_model
        url = f"{self.base_url}/models/{model}:generateContent?key={self._key}"
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        }
        try:
            r = requests.post(url, json=body, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException as exc:
            raise ProviderError(self.name, "network", exc.__class__.__name__) from exc
        if r.status_code != 200:
            raise ProviderError(self.name, r.status_code, "non-200")
        try:
            data = r.json()
            text_parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            content = "".join(p.get("text", "") for p in text_parts)
        except (KeyError, IndexError, TypeError, ValueError):
            content = ""
        return ChatResponse(provider=self.name, model=model, content=content)


@dataclass
class ProviderChain:
    """依序嘗試 providers，遇到可重試錯誤切下一個。

    可重試判定：HTTP 429 / 5xx / network / no_key / unsupported。
    其他錯誤（例如 400 prompt 不合法）會立刻 raise，避免無效重試浪費 token。
    """

    providers: list[ChatProvider]

    RETRYABLE_HTTP: tuple[int | str, ...] = (
        "no_key", "network", "unsupported", 408, 429, 500, 502, 503, 504,
    )

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> ChatResponse:
        last_err: ProviderError | None = None
        for provider in self.providers:
            if tools and not provider.supports_tools:
                continue
            try:
                return provider.chat_with_tools(
                    messages=messages,
                    tools=tools,
                    model=model if _is_model_for(provider, model) else None,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tool_choice=tool_choice,
                )
            except ProviderError as exc:
                last_err = exc
                if exc.http_status not in self.RETRYABLE_HTTP:
                    raise
                continue
        if last_err is None:
            raise ProviderError("chain", "empty", "no providers configured")
        raise last_err


def _is_model_for(provider: ChatProvider, model: str | None) -> bool:
    """若 caller 指定特定模型名稱，僅傳給對應 provider；其他 provider 用各自 default_model。"""
    if not model:
        return False
    if model.startswith("MiniMax"):
        return provider.name == "minimax"
    if model.startswith("glm"):
        return provider.name == "glm"
    if model.startswith("gemini"):
        return provider.name == "gemini"
    return False


def build_default_chain() -> ProviderChain:
    """專案預設 chain：MiniMax → GLM → (Gemini 不支援 tool, 自動跳過)。"""
    return ProviderChain(
        providers=[MiniMaxProvider(), GLMProvider(), GeminiProvider()],
    )


def public_status_snapshot(providers: Iterable[ChatProvider] | None = None) -> list[dict[str, Any]]:
    """回傳可公開的 provider 狀態快照（不含 key 值），用於 admin 或除錯。"""
    providers = list(providers or build_default_chain().providers)
    return [
        {
            "name": p.name,
            "default_model": p.default_model,
            "supports_tools": p.supports_tools,
            "key_present": bool(getattr(p, "available", False)),
        }
        for p in providers
    ]
