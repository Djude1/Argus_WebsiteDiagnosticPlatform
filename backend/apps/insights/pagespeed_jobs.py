"""快速檢查頁「網站測速」的 Google PageSpeed Insights 量測（2026-10-09）。

量測一次要 20～60 秒，不能在 web 請求裡同步等（正式站 web 只有 2 workers × 4 threads，
幾個免登入請求就會卡滿），所以交給 Celery 背景執行、結果放 Django cache（正式環境是 Redis），
前端用 job 代號輪詢。

- 只在平台設定了 `ARGUS_PAGESPEED_API_KEY` 時啟用（與完整掃描共用 `apps.scans.pagespeed`）。
- 同一個網址 10 分鐘內重複測速直接回快取，省 Google 配額。
- 受測網址已先通過 `assert_public_url`；量測由 Google 機房發出，不會從我們的主機連到受測網址。
"""

from __future__ import annotations

import hashlib
import re
import secrets

from django.core.cache import cache

from apps.scans import pagespeed

JOB_TTL_SECONDS = 15 * 60
URL_CACHE_SECONDS = 10 * 60
JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def _job_key(job_id: str) -> str:
    return f"insights:psi:job:{job_id}"


def _url_key(url: str) -> str:
    return "insights:psi:url:" + hashlib.sha256(url.encode()).hexdigest()


def start(url: str) -> dict:
    """排入量測並回傳給前端的狀態：unavailable／done（快取）／pending（附 job）／failed。"""
    if not pagespeed.enabled():
        return {"status": "unavailable"}
    cached = cache.get(_url_key(url))
    if cached:
        return {**cached, "cached": True}
    from apps.insights.tasks import run_public_pagespeed

    job_id = secrets.token_urlsafe(18)
    cache.set(_job_key(job_id), {"status": "pending"}, JOB_TTL_SECONDS)
    try:
        run_public_pagespeed.delay(job_id, url)
    except Exception:
        cache.delete(_job_key(job_id))
        return {"status": "failed", "reason": "暫時無法排入 Google 量測，請稍後再試。"}
    # 測試或 CELERY_TASK_ALWAYS_EAGER 時任務已同步跑完，直接回最終結果
    return {**(get(job_id) or {"status": "pending"}), "job": job_id}


def run(job_id: str, url: str) -> None:
    """Celery 任務本體：呼叫 PSI，結果寫回 cache。"""
    try:
        payload = {"status": "done", "report": pagespeed.fetch(url)}
    except pagespeed.PageSpeedError as exc:
        payload = {"status": "failed", "reason": str(exc)}
    except Exception:
        payload = {"status": "failed", "reason": "Google 量測發生未預期的錯誤。"}
    cache.set(_job_key(job_id), payload, JOB_TTL_SECONDS)
    if payload["status"] == "done":
        cache.set(_url_key(url), payload, URL_CACHE_SECONDS)


def get(job_id: str) -> dict | None:
    if not JOB_ID_RE.match(job_id or ""):
        return None
    return cache.get(_job_key(job_id))
