"""從爬蟲已存的 DOM 組出「原樣複刻」，不呼叫任何模型。

複刻刻意**不走 LLM**：爬蟲階段已經把 rendered_dom 存進 Page，要重現那一頁
只需要把 DOM 寫回檔案並補一個 <base>。交給模型「推理出一個長得一樣的頁面」
既貴又不可能逐字一致——模型能加值的是後面的優化階段，不是這裡。
"""

from __future__ import annotations

import re

# 只比對開頭的 <head ...>，避免誤中內文裡出現的字串
_HEAD_OPEN = re.compile(r"<head\b[^>]*>", re.IGNORECASE)
_EXISTING_BASE = re.compile(r"<base\b[^>]*>", re.IGNORECASE)
_HTML_OPEN = re.compile(r"<html\b[^>]*>", re.IGNORECASE)


def _escape_attr(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def build_snapshot_html(page) -> str:
    """回傳可獨立開啟的複刻 HTML。

    rendered_dom 是 Playwright 執行 JS 後的結果，比原始 html 更接近使用者
    真正看到的樣子，所以優先用它；爬蟲若因逾時沒拿到才退回 html。
    """
    source = (page.rendered_dom or page.html or "").strip()
    if not source:
        raise ValueError("此頁沒有可用的 DOM，無法複刻")

    # 沒有 <base> 的話，DOM 裡所有相對路徑（CSS/JS/圖片）都會相對於 Argus
    # 自己的網域解析，複刻出來會是一頁沒有樣式的純文字。
    if _EXISTING_BASE.search(source):
        return source

    base_url = page.final_url or page.url
    base_tag = f'<base href="{_escape_attr(base_url)}">'

    head_match = _HEAD_OPEN.search(source)
    if head_match:
        return source[: head_match.end()] + base_tag + source[head_match.end() :]

    html_match = _HTML_OPEN.search(source)
    if html_match:
        return (
            source[: html_match.end()]
            + f"<head>{base_tag}</head>"
            + source[html_match.end() :]
        )

    return f"<head>{base_tag}</head>{source}"
