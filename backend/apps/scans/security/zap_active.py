"""OWASP ZAP 主動掃描（spider＋active scan）：對目標實際送出攻擊 payload。

**只在「全站＋主動模式＋網域已驗證」的授權掃描**由 tasks.py 呼叫（`scan_plan.run_zap_active`
把關），且要 `ARGUS_ZAP_ACTIVE_ENABLED=true`。與被動分析（`zap_passive`）互補：被動從爬蟲
已錄的 HAR 找問題、對目標零新增請求；主動會真的送請求試探弱點。

繞過 Cloudflare 的關鍵：**先把爬蟲的 HAR 匯進 ZAP 建站台樹**（Playwright 已繞過 CF 抓到真實
URL），再對這些節點做 active scan；不完全依賴 ZAP 自己的 spider（spider 在 CF 後面會被擋到
幾乎抓不到東西）。

結束時一律清掉 ZAP 上這個網站的告警、節點，並把上傳的 HAR 覆寫成 `{}`。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.core.cache import cache

from apps.scans.security.zap_passive import (
    ZapBusy,
    ZapClient,
    ZapError,
    build_har,
)


@dataclass
class ZapActiveResult:
    version: str = ""
    alerts: list[dict] = field(default_factory=list)
    scanned: bool = False       # active scan 是否真的對節點跑了
    completed: bool = True      # 是否在時限內跑完（False＝逾時／被停）
    reason: str = ""            # scanned=False 時的原因（給覆蓋說明用）


def _poll(
    status_fn: Callable[[str], int], scan_id: str, deadline: float,
    cancel_check: Callable[[], None], stop: Callable[[str], None],
) -> bool:
    """輪詢 ZAP 掃描進度到 100 或逾時；逾時就停掉。回傳是否跑完。"""
    while True:
        cancel_check()
        if status_fn(scan_id) >= 100:
            return True
        if time.monotonic() > deadline:
            stop(scan_id)
            return False
        time.sleep(2)


def run_active(
    har_paths: list[Path], origin: str, scan_id: int,
    *, cancel_check: Callable[[], None] = lambda: None, client: ZapClient | None = None,
) -> ZapActiveResult:
    """對 origin 做 ZAP 主動掃描；先用爬蟲 HAR 建站台樹再 active scan。結束後清乾淨。"""
    payload, count = build_har(har_paths, origin)
    lock_key = f"argus-zap:{origin.lower()}"
    lock_ttl = int(settings.ARGUS_ZAP_ACTIVE_TIMEOUT_SECONDS) + 180
    if not cache.add(lock_key, scan_id, timeout=lock_ttl):
        raise ZapBusy("同一個網站的另一次掃描正在使用 ZAP")
    client = client or ZapClient(settings.ARGUS_ZAP_API_URL, settings.ARGUS_ZAP_API_KEY)
    file_name = f"argus-active-{scan_id}.har"
    uploaded = False
    spider_id = ""
    ascan_id = ""
    try:
        result = ZapActiveResult(version=client.version())
        client.clear_origin(origin)
        # 1. 用爬蟲 HAR 建站台樹（繞過 CF）；沒有流量時仍嘗試 spider
        if count:
            path = client.upload(file_name, payload)
            uploaded = True
            client.action("exim", "importHar", filePath=path)

        total_deadline = time.monotonic() + settings.ARGUS_ZAP_ACTIVE_TIMEOUT_SECONDS

        # 2. spider（有限時間；CF 後多半無效，有 HAR 建樹就夠）
        try:
            spider_id = client.spider_scan(origin)
            if spider_id.lstrip("-").isdigit():
                spider_deadline = min(
                    total_deadline,
                    time.monotonic() + settings.ARGUS_ZAP_ACTIVE_SPIDER_SECONDS,
                )
                _poll(client.spider_status, spider_id, spider_deadline, cancel_check,
                      client.spider_stop)
        except ZapError:
            spider_id = ""  # spider 起不來不影響 active scan（靠 HAR 建的樹）

        cancel_check()

        # 3. active scan：對站台樹中 origin 底下的節點送攻擊 payload
        try:
            ascan_id = client.ascan_scan(origin)
        except ZapError as exc:
            # 沒有可攻擊的節點（HAR 空＋spider 被擋）→ 標記未掃，不算失敗
            result.reason = f"沒有可主動掃描的節點（{exc}）"
            result.alerts = client.alerts(origin)
            return result
        if not ascan_id.lstrip("-").isdigit():
            result.reason = "ZAP 未建立 active scan（可能無可掃描節點）"
            result.alerts = client.alerts(origin)
            return result

        result.scanned = True
        result.completed = _poll(
            client.ascan_status, ascan_id, total_deadline, cancel_check, client.ascan_stop
        )
        cancel_check()
        result.alerts = client.alerts(origin)
        return result
    finally:
        if ascan_id:
            client.ascan_stop(ascan_id)
        if spider_id:
            client.spider_stop(spider_id)
        client.clear_origin(origin)
        if uploaded:
            try:
                client.upload(file_name, "{}")  # 流量內容不留在 ZAP 主機上
            except ZapError:
                pass
        cache.delete(lock_key)


def active_enabled() -> bool:
    from apps.scans.security.zap_passive import enabled as zap_enabled

    return bool(settings.ARGUS_ZAP_ACTIVE_ENABLED and zap_enabled())
