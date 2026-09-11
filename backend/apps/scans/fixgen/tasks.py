"""修正產出的 Celery 任務。

不加重試：產生會花 token，自動重試等於在使用者沒同意下重複計費
（與 rebuild 任務同一條規則）。
"""

from __future__ import annotations

from celery import shared_task


@shared_task
def run_fix_output_task(scan_job_id: int) -> None:
    from apps.scans.fixgen.services import run_fix_output

    run_fix_output(scan_job_id)
