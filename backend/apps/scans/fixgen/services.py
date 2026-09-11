"""FixOutput 狀態機（idle → generating → ready / failed）與冪等觸發。

狀態轉換以條件式 update 原子搶占：併發觸發只有一個贏家會派工，
其餘拿到既有結果——「每份 ScanJob 只產一次」由此保證。
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.utils import timezone

from apps.agent.providers import (
    ProviderChain,
    ProviderError,
    build_default_chain,
)
from apps.billing.services import charge_fixgen_generation, refund_fixgen_generation
from apps.scans.fixgen.engine import FixgenError, generate_artifacts
from apps.scans.fixgen.tasks import run_fix_output_task
from apps.scans.models import FixOutput, ScanJob

logger = logging.getLogger(__name__)


class FixgenDisabledError(Exception):
    """修正產出功能未啟用（ARGUS_FIXGEN_ENABLED）。"""


def trigger_fix_output(scan_job: ScanJob) -> tuple[FixOutput, bool]:
    """API 觸發入口：計費閘門＋冪等派工。

    點數必須在派工之前扣（同 rebuild 規則）：餘額不足的人不能先讓 LLM
    把 token 花掉。已產生中／已完成 → 不計費不派工（冪等）。極罕見的
    併發搶輸（另一請求先派工）→ 退回剛才的計費。
    """
    if not settings.ARGUS_FIXGEN_ENABLED:
        raise FixgenDisabledError("ARGUS_FIXGEN_ENABLED")

    fix_output, _created = FixOutput.objects.get_or_create(scan_job=scan_job)
    if fix_output.status in (FixOutput.Status.GENERATING, FixOutput.Status.READY):
        return fix_output, False

    charge_fixgen_generation(scan_job.user, scan_job)  # InsufficientCoinError 往上拋
    fix_output, dispatched = start_fix_output(scan_job)
    if not dispatched:
        try:
            refund_fixgen_generation(scan_job.user, scan_job)
        except Exception:  # noqa: BLE001
            logger.exception(
                "fixgen: 併發搶輸後退款失敗 scan_job=%s（可手動補退）", scan_job.id
            )
    return fix_output, dispatched


def start_fix_output(scan_job: ScanJob) -> tuple[FixOutput, bool]:
    """冪等觸發修正產出。回傳 (fix_output, dispatched)。

    - 尚未產生（idle）→ 轉 generating 並派 Celery 任務
    - 產生中／已完成 → 直接回傳，不重複派工（不重複計費）
    - 曾失敗（failed）→ 允許重試
    """
    fix_output, _created = FixOutput.objects.get_or_create(scan_job=scan_job)
    if fix_output.status in (FixOutput.Status.GENERATING, FixOutput.Status.READY):
        return fix_output, False
    updated = FixOutput.objects.filter(
        pk=fix_output.pk,
        status__in=(FixOutput.Status.IDLE, FixOutput.Status.FAILED),
    ).update(status=FixOutput.Status.GENERATING, error="")
    if not updated:
        return FixOutput.objects.get(pk=fix_output.pk), False
    run_fix_output_task.delay(scan_job.id)
    return FixOutput.objects.get(pk=fix_output.pk), True


def run_fix_output(scan_job_id: int, chain: ProviderChain | None = None) -> None:
    """Celery task 本體。測試以假 chain 注入（spec Seam 1：產生服務邊界）。"""
    fix_output = (
        FixOutput.objects.select_related("scan_job")
        .filter(scan_job_id=scan_job_id, status=FixOutput.Status.GENERATING)
        .first()
    )
    if fix_output is None:
        # 重複／過期任務——冪等忽略
        return

    if not settings.ARGUS_FIXGEN_ENABLED:
        _fail(fix_output, "修正產出功能未啟用（ARGUS_FIXGEN_ENABLED）")
        return

    try:
        artifacts, meta = generate_artifacts(
            fix_output.scan_job, chain=chain or build_default_chain()
        )
    except FixgenError as exc:
        _fail(fix_output, str(exc))
        return
    except ProviderError as exc:
        # ProviderError 只帶公開資訊（provider / http 狀態），可安全顯示
        _fail(fix_output, f"產生失敗：LLM provider 無法回應（{exc.provider}）")
        return
    except Exception:
        logger.exception("fixgen: 未預期的產生失敗 scan_job=%s", scan_job_id)
        _fail(fix_output, "產生失敗：內部錯誤，請稍後再試")
        return

    fix_output.status = FixOutput.Status.READY
    fix_output.artifacts = artifacts
    fix_output.provider = meta["provider"]
    fix_output.model_id = meta["model"]
    fix_output.total_tokens = meta["total_tokens"]
    fix_output.error = ""
    fix_output.generated_at = timezone.now()
    fix_output.save(
        update_fields=[
            "status", "artifacts", "provider", "model_id",
            "total_tokens", "error", "generated_at", "updated_at",
        ]
    )


def _fail(fix_output: FixOutput, message: str) -> None:
    """唯一失敗收斂路徑：狀態轉 failed + 可公開原因 + 退費。

    產生失敗不為沒拿到的產出收費（spec）：點數退點、附贈額度返還——
    refund_fixgen_generation 本身冪等，未計費過的（如功能未啟用直接
    落 failed）是 no-op。退費失敗不蓋掉原本的失敗原因，只記 log。
    """
    fix_output.status = FixOutput.Status.FAILED
    fix_output.error = message[:255]
    fix_output.save(update_fields=["status", "error", "updated_at"])
    try:
        refund_fixgen_generation(fix_output.scan_job.user, fix_output.scan_job)
    except Exception:  # noqa: BLE001
        logger.exception(
            "fixgen: 失敗退費未完成 scan_job=%s（可手動補退）", fix_output.scan_job_id
        )
