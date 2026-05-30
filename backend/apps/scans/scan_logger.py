"""ScanJob 執行日誌工具。

每筆 log entry 格式：
  {"t": "2026-05-28T10:00:00.123456+00:00", "lvl": "info"|"warn"|"error", "msg": "..."}

設計原則：
- append_log() 用 F 運算子做 array append，避免整段 JSON 回讀
- Django JSONField 不支援原生 array append，改用 read-modify-write
  但以 update_fields=["scan_log"] 最小化寫入欄位
- 最多保留 MAX_LOG_ENTRIES 筆，超過自動捨棄最舊的
"""
from __future__ import annotations

from django.utils import timezone

MAX_LOG_ENTRIES = 200


def append_log(scan_job_id: int, msg: str, level: str = "info") -> None:
    """在 ScanJob.scan_log 末尾追加一筆記錄。"""
    from apps.scans.models import ScanJob

    entry = {"t": timezone.now().isoformat(), "lvl": level, "msg": msg}
    try:
        job = ScanJob.objects.only("scan_log").get(pk=scan_job_id)
        log = list(job.scan_log or [])
        log.append(entry)
        if len(log) > MAX_LOG_ENTRIES:
            log = log[-MAX_LOG_ENTRIES:]
        ScanJob.objects.filter(pk=scan_job_id).update(scan_log=log)
    except ScanJob.DoesNotExist:
        pass
    except Exception:  # noqa: BLE001
        pass  # log 寫入失敗不應影響主流程
