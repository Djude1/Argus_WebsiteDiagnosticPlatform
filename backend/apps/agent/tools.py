"""Hermes-Agent 可呼叫的 Playwright tools。

設計原則：
- 以 OpenAI function calling 格式定義 schema，讓 MiniMax / GLM 直接相容。
- ToolExecutor 接收 async Page，將 LLM 的 tool call 轉成 Playwright 動作。
- 所有 tool 回傳 JSON-serializable dict；長字串截短，避免吃光 context。
- selector 走 Playwright 標準語法（CSS / role / text），不執行任意 JS。
- report_ux_issue 不在這裡落地，executor 只把資料回傳；loop 層負責寫入 Finding。
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

DEFAULT_ACTION_TIMEOUT_MS = 5000
MAX_TEXT_BYTES = 4000
MAX_DOM_NODES = 80


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "點擊符合 CSS selector 的第一個元素。",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector"},
                },
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "在符合 selector 的輸入元素填入文字（會清掉原內容）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["selector", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "捲動頁面：direction up/down，amount 為像素。",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down"]},
                    "amount": {"type": "integer", "minimum": 50, "maximum": 5000},
                },
                "required": ["direction", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_visible_text",
            "description": "取得目前 viewport 內可見的純文字摘要，已截短。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dom_summary",
            "description": "取得頁面互動元素摘要（最多前 80 個，含 tag、role、可見文字）。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "對目前 viewport 截圖並儲存，回傳檔案路徑。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_ux_issue",
            "description": "回報一個 UX 問題；不要回報修復程式碼，只描述問題與方向。",
            "parameters": {
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low", "info"],
                    },
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "remediation": {"type": "string"},
                    "selector": {"type": "string"},
                },
                "required": ["severity", "title", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "完成本次任務並結束。當你已經回報完所有發現或無法繼續時呼叫。",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                },
            },
        },
    },
]


@dataclass
class ToolOutcome:
    """單一 tool 執行結果。"""

    ok: bool
    result: dict[str, Any]
    finish: bool = False  # finish/error 達成終止條件
    issue: dict[str, Any] | None = None  # report_ux_issue 的 payload


def _truncate(text: str, limit: int = MAX_TEXT_BYTES) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"...[truncated {len(text) - limit} chars]"


class ToolExecutor:
    """把 LLM 的 tool call 轉成 Playwright 動作。

    傳入 page 必須是 async Playwright Page；screenshot_dir 用於存截圖。
    """

    def __init__(
        self,
        page: Page,
        screenshot_dir: str,
        action_timeout_ms: int = DEFAULT_ACTION_TIMEOUT_MS,
    ):
        self.page = page
        self.screenshot_dir = screenshot_dir
        self.action_timeout_ms = action_timeout_ms
        self._screenshot_counter = 0

    async def run(self, name: str, args: dict[str, Any]) -> ToolOutcome:
        try:
            if name == "click":
                return await self._click(args.get("selector", ""))
            if name == "type_text":
                return await self._type_text(args.get("selector", ""), args.get("text", ""))
            if name == "scroll":
                return await self._scroll(
                    args.get("direction", "down"), int(args.get("amount", 500))
                )
            if name == "get_visible_text":
                return await self._get_visible_text()
            if name == "get_dom_summary":
                return await self._get_dom_summary()
            if name == "take_screenshot":
                return await self._take_screenshot()
            if name == "report_ux_issue":
                return self._report_ux_issue(args)
            if name == "finish":
                return ToolOutcome(
                    ok=True,
                    result={"summary": str(args.get("summary", ""))[:500]},
                    finish=True,
                )
            return ToolOutcome(ok=False, result={"error": f"unknown_tool:{name}"})
        except PlaywrightTimeoutError as exc:
            return ToolOutcome(ok=False, result={"error": "timeout", "detail": str(exc)[:200]})
        except Exception as exc:
            return ToolOutcome(
                ok=False,
                result={"error": exc.__class__.__name__, "detail": str(exc)[:200]},
            )

    async def _click(self, selector: str) -> ToolOutcome:
        if not selector:
            return ToolOutcome(ok=False, result={"error": "empty_selector"})
        loc = self.page.locator(selector).first
        await loc.click(timeout=self.action_timeout_ms)
        await self.page.wait_for_load_state("domcontentloaded", timeout=self.action_timeout_ms)
        url = self.page.url
        return ToolOutcome(ok=True, result={"clicked": selector, "url_after": url})

    async def _type_text(self, selector: str, text: str) -> ToolOutcome:
        if not selector:
            return ToolOutcome(ok=False, result={"error": "empty_selector"})
        loc = self.page.locator(selector).first
        await loc.fill(text, timeout=self.action_timeout_ms)
        return ToolOutcome(ok=True, result={"typed_into": selector, "length": len(text)})

    async def _scroll(self, direction: str, amount: int) -> ToolOutcome:
        delta = amount if direction == "down" else -amount
        await self.page.evaluate("(d) => window.scrollBy(0, d)", delta)
        await asyncio.sleep(0.2)
        return ToolOutcome(ok=True, result={"scrolled": delta})

    async def _get_visible_text(self) -> ToolOutcome:
        text = await self.page.evaluate(
            "() => document.body && document.body.innerText ? document.body.innerText : ''"
        )
        return ToolOutcome(ok=True, result={"text": _truncate(str(text))})

    async def _get_dom_summary(self) -> ToolOutcome:
        # 注意：JS 模板內 .slice(0, 60) 那行因 JSON 結構需保持單行；用 noqa 略過 ruff 行長檢查
        script = (
            "() => {\n"
            "  const out = [];\n"
            "  const tags = ['a', 'button', 'input', 'select', 'textarea', 'form', 'nav'];\n"
            "  for (const tag of tags) {\n"
            "    const els = document.querySelectorAll(tag);\n"
            f"    for (let i = 0; i < els.length && out.length < {MAX_DOM_NODES}; i++) {{\n"
            "      const el = els[i];\n"
            "      const rect = el.getBoundingClientRect();\n"
            "      if (rect.width === 0 || rect.height === 0) continue;\n"
            "      out.push({\n"
            "        tag,\n"
            "        role: el.getAttribute('role') || '',\n"
            "        name: (el.getAttribute('aria-label') || el.getAttribute('placeholder')"
            " || (el.innerText || '').slice(0, 60)).trim(),\n"
            "        href: el.getAttribute('href') || '',\n"
            "        id: el.id || '',\n"
            "      });\n"
            "    }\n"
            "  }\n"
            "  return out;\n"
            "}"
        )
        nodes = await self.page.evaluate(script)
        return ToolOutcome(ok=True, result={"nodes": nodes[:MAX_DOM_NODES]})

    async def _take_screenshot(self) -> ToolOutcome:
        self._screenshot_counter += 1
        from pathlib import Path

        path = Path(self.screenshot_dir) / f"agent_step_{self._screenshot_counter}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        await self.page.screenshot(path=str(path), full_page=False)
        return ToolOutcome(ok=True, result={"path": str(path)})

    def _report_ux_issue(self, args: dict[str, Any]) -> ToolOutcome:
        severity = args.get("severity", "low")
        title = (args.get("title") or "").strip()[:255]
        description = (args.get("description") or "").strip()
        remediation = (args.get("remediation") or "").strip()
        selector = (args.get("selector") or "").strip()[:512]

        # 防呆：若描述夾帶程式碼修復片段，仍保留但 strip 過長
        description = description[:5000]
        remediation = remediation[:5000]

        if not title or not description:
            return ToolOutcome(ok=False, result={"error": "missing_title_or_description"})

        valid_sev = {"critical", "high", "medium", "low", "info"}
        payload = {
            "severity": severity if severity in valid_sev else "low",
            "title": title,
            "description": description,
            "remediation": remediation or "請檢視該流程的可用性並對齊使用者預期。",
            "selector": selector,
            "url": self.page.url,
        }
        return ToolOutcome(ok=True, result={"reported": True, "title": title}, issue=payload)
