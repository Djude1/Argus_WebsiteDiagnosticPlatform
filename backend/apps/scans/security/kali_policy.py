"""Kali SQLmap 共用授權、目標驗證與原子預算保留政策。"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from urllib.parse import parse_qsl, urlsplit

from django.conf import settings
from redis import Redis

from apps.scans.cancellation import ScanCancelled
from apps.scans.models import ScanJob
from apps.scans.services import (
    PublicScanTargetError,
    assert_public_http_url,
    get_origin,
)

from .kali_contracts import ReservationOutcome, ReservedSqlmapTarget

_ALLOWED_BACKENDS = {"docker", "kubernetes"}
_RESERVE_TARGETS_LUA = """
local now = tonumber(redis.call("TIME")[1])
local started = redis.call("GET", KEYS[2])
if not started then
  redis.call("SET", KEYS[2], now, "EX", ARGV[3], "NX")
  started = now
end
if now - tonumber(started) >= tonumber(ARGV[1]) then
  return {-1}
end

local used = redis.call("SCARD", KEYS[1])
local admitted = {}
for index = 4, #ARGV do
  if used >= tonumber(ARGV[2]) then break end
  if redis.call("SISMEMBER", KEYS[1], ARGV[index]) == 0 then
    redis.call("SADD", KEYS[1], ARGV[index])
    used = used + 1
    table.insert(admitted, index - 4)
  end
end
redis.call("EXPIRE", KEYS[1], ARGV[3])
redis.call("EXPIRE", KEYS[2], ARGV[3])
return admitted
"""


def get_kali_redis() -> Redis:
    return Redis.from_url(
        settings.ARGUS_KALI_REDIS_URL,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


def reserve_sqlmap_targets(
    scan_job_id: int,
    candidate_urls: Sequence[str],
    *,
    max_count: int,
) -> ReservationOutcome:
    if not settings.ARGUS_KALI_ENABLED:
        return ReservationOutcome(blocked_reason="kali_disabled")
    if settings.ARGUS_KALI_BACKEND not in _ALLOWED_BACKENDS:
        return ReservationOutcome(blocked_reason="backend_misconfigured")

    try:
        scan = ScanJob.objects.only(
            "status",
            "scan_mode",
            "active_testing_authorized",
            "origin",
        ).get(pk=scan_job_id)
    except ScanJob.DoesNotExist:
        return ReservationOutcome(blocked_reason="scan_not_found")
    if scan.status == ScanJob.Status.CANCELLED:
        raise ScanCancelled()
    if scan.scan_mode != ScanJob.ScanMode.ACTIVE:
        return ReservationOutcome(blocked_reason="scan_mode_not_active")
    if not scan.active_testing_authorized:
        return ReservationOutcome(blocked_reason="active_testing_unauthorized")

    selected_urls = list(candidate_urls[: max(0, max_count)])
    if not selected_urls:
        return ReservationOutcome()

    candidates: list[ReservedSqlmapTarget] = []
    for index, raw_url in enumerate(selected_urls):
        try:
            normalized = assert_public_http_url(raw_url)
        except PublicScanTargetError:
            return ReservationOutcome(blocked_reason="target_not_public")
        except (AttributeError, TypeError, ValueError):
            return ReservationOutcome(blocked_reason="invalid_target_url")
        if get_origin(normalized) != scan.origin:
            return ReservationOutcome(blocked_reason="cross_origin_forbidden")
        if not parse_qsl(urlsplit(normalized).query, keep_blank_values=True):
            return ReservationOutcome(blocked_reason="no_query_parameter")
        fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        candidates.append(ReservedSqlmapTarget(index, normalized, fingerprint))

    targets_key = f"argus:kali:scan:{scan_job_id}:targets"
    started_key = f"argus:kali:scan:{scan_job_id}:started"
    client = get_kali_redis()
    admitted = [
        int(value)
        for value in client.eval(
            _RESERVE_TARGETS_LUA,
            2,
            targets_key,
            started_key,
            settings.ARGUS_KALI_SCAN_DEADLINE_SECONDS,
            min(settings.ARGUS_KALI_MAX_TARGETS, 3),
            settings.ARGUS_KALI_STATE_TTL_SECONDS,
            *(candidate.fingerprint for candidate in candidates),
        )
    ]
    if admitted == [-1]:
        return ReservationOutcome(blocked_reason="scan_deadline_exceeded")
    if not admitted:
        already_tested = all(
            client.sismember(targets_key, candidate.fingerprint)
            for candidate in candidates
        )
        reason = "target_already_tested" if already_tested else "scan_budget_exhausted"
        return ReservationOutcome(blocked_reason=reason)
    return ReservationOutcome(targets=tuple(candidates[index] for index in admitted))
