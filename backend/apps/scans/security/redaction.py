"""掃描 finding、log 與工具輸出的共用敏感資料遮罩。"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from apps.scans.scanners import (
    CREDIT_CARD_PATTERN,
    EMAIL_PATTERN,
    TW_MOBILE_PATTERN,
    TW_NATIONAL_ID_PATTERN,
)


def _mask_email(match: re.Match) -> str:
    email = match.group(0)
    local, _, domain = email.partition("@")
    visible = local[:2]
    return f"{visible}{'*' * max(len(local) - len(visible), 1)}@{domain}"


def _mask_digits(match: re.Match, keep_start: int, keep_end: int) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    if len(digits) <= keep_start + keep_end:
        return "*" * len(digits)
    return (
        digits[:keep_start]
        + "*" * (len(digits) - keep_start - keep_end)
        + digits[-keep_end:]
    )


def redact_pii_in_text(text: str) -> str:
    """遮罩 email、台灣手機、身分證與信用卡格式，只保留人工比對所需頭尾。"""
    if not text:
        return text
    masked = EMAIL_PATTERN.sub(_mask_email, text)
    masked = TW_MOBILE_PATTERN.sub(lambda m: _mask_digits(m, 2, 2), masked)
    masked = TW_NATIONAL_ID_PATTERN.sub(lambda m: m.group(0)[0] + "*" * 8, masked)
    return CREDIT_CARD_PATTERN.sub(lambda m: _mask_digits(m, 4, 4), masked)


def redact_url_query_values(url: str) -> str:
    """保留 URL query key、遮罩所有 value，並移除 fragment。"""
    parsed = urlsplit(url or "")
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    query = urlencode([(key, "[REDACTED]") for key, _value in pairs])
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))


def redact_warning_summary(value):
    """遞迴遮罩爬蟲警告中的 URL query 與個資，再交給 DB／log 持久化。"""
    if isinstance(value, dict):
        return {key: redact_warning_summary(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_warning_summary(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_warning_summary(item) for item in value)
    if not isinstance(value, str):
        return value

    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        value = redact_url_query_values(value)
    return redact_pii_in_text(value)


def mask_sensitive_value(value: str) -> str:
    """遮罩工具回報的任意敏感值；短值也絕不原樣回傳。"""
    value = (value or "").strip()
    if not value:
        return ""
    return f"[REDACTED:{len(value)}]"
