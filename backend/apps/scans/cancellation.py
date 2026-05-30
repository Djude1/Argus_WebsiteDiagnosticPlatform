"""合作式（cooperative）掃描終止機制。

API endpoint 把 ScanJob.status 設為 CANCELLED 後立刻回應；Celery worker 在各階段
檢查點透過 `raise_if_cancelled` 主動 raise ScanCancelled。tasks.py 主迴圈
的 try/except 分流：CANCELLED 不算失敗，補上 completed_at 與清空 progress 即可。

選擇「合作式」而非 Celery `revoke(terminate=True)` 的理由：
- terminate 會送 SIGTERM 給 worker process，可能造成同 worker 上其他 task
  被影響或 worker 重啟。
- 合作式 cancel 讓 worker 在「安全點」停下，DB 不會留下半完成的不一致狀態。
"""

from __future__ import annotations


class ScanCancelled(Exception):
    """掃描被使用者主動終止。tasks.py 主 try/except 應該分流不算失敗。"""


def is_cancelled(scan_job_id: int) -> bool:
    """查 DB 即時狀態（不用 ORM 物件快取）判斷是否已被 cancel。"""
    # 延遲 import 避免循環
    from apps.scans.models import ScanJob

    return ScanJob.objects.filter(
        id=scan_job_id, status=ScanJob.Status.CANCELLED
    ).exists()


def raise_if_cancelled(scan_job_id: int) -> None:
    """檢查點：若已被 cancel 就 raise ScanCancelled。"""
    if is_cancelled(scan_job_id):
        raise ScanCancelled()
