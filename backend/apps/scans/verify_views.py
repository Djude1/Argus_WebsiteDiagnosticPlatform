"""報告查驗：公開端點，讓收到 .docx 的第三方核對報告真偽。

刻意不需要登入——收件者通常不是 Argus 的使用者。因此回應內容嚴格限制在
「這份報告在講哪個網站、什麼時候掃的、拿幾分」，**絕不揭露掃描發起人是誰**，
否則等於用報告編號就能反查使用者身分。
"""

from __future__ import annotations

from config.throttling import AnonRateThrottle
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.scans.models import ReportVerification


@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([AnonRateThrottle])
def verify_report(request, report_number: str):
    try:
        record = ReportVerification.objects.select_related("scan_job").get(
            report_number=report_number
        )
    except ReportVerification.DoesNotExist:
        return Response(
            {"detail": "查無此報告編號。這份報告可能不是由 Argus 出具，或編號輸入有誤。"},
            status=status.HTTP_404_NOT_FOUND,
        )

    scan_job = record.scan_job
    return Response({
        "report_number": record.report_number,
        "scan_target": scan_job.normalized_url,
        "scanned_at": scan_job.completed_at.isoformat() if scan_job.completed_at else None,
        "generated_at": record.generated_at.isoformat(),
        "overall_score": scan_job.overall_score,
        "content_sha256": record.content_sha256,
    })
