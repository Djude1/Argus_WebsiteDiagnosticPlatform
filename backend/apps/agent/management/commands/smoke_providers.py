"""對 LLM provider 做安全 smoke test。

依 skills/argus-project/references/api-provider-workflow.md：
只輸出 provider / HTTP / 能力摘要，不輸出 key、headers、raw body。
未來換 key 或新增 provider 時用：
    uv run python backend/manage.py smoke_providers
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.agent.providers import (
    GeminiProvider,
    GLMProvider,
    MiniMaxProvider,
    ProviderError,
    public_status_snapshot,
)

PING_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "ping",
            "description": "ping",
            "parameters": {
                "type": "object",
                "properties": {"arg": {"type": "integer"}},
                "required": ["arg"],
            },
        },
    }
]
PING_MESSAGES = [
    {"role": "system", "content": "You are a test bot."},
    {"role": "user", "content": "Call ping with arg=42."},
]


class Command(BaseCommand):
    help = "對 MiniMax / GLM / Gemini 做安全的能力探測（不輸出秘密）。"

    def handle(self, *args, **options):
        self.stdout.write("# Provider snapshot (no secrets printed)")
        for row in public_status_snapshot():
            self.stdout.write(
                f"  {row['name']:8} default={row['default_model']:24} "
                f"tools={row['supports_tools']} key_present={row['key_present']}"
            )

        self.stdout.write("\n# Smoke tests")
        self._smoke_chat("minimax", MiniMaxProvider(), tool_calling=True)
        self._smoke_chat("glm", GLMProvider(), tool_calling=True)
        self._smoke_chat("gemini", GeminiProvider(), tool_calling=False)

    def _smoke_chat(self, label: str, provider, tool_calling: bool) -> None:
        if not getattr(provider, "available", False):
            self.stdout.write(f"  {label:8} skip   no_key")
            return
        try:
            if tool_calling:
                resp = provider.chat_with_tools(
                    messages=PING_MESSAGES,
                    tools=PING_TOOL,
                    max_tokens=64,
                )
                self.stdout.write(
                    f"  {label:8} pass   model={resp.model} "
                    f"tool_calls={'yes' if resp.tool_calls else 'no'} "
                    f"tokens={resp.total_tokens}"
                )
            else:
                resp = provider.chat_text("Reply with a single word: OK")
                first_line = (resp.content or "").splitlines()[0][:40]
                self.stdout.write(
                    f"  {label:8} pass   model={resp.model} sample={first_line!r}"
                )
        except ProviderError as exc:
            self.stdout.write(
                f"  {label:8} fail   http={exc.http_status} hint={exc.hint}"
            )
