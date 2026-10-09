from config.throttling import AnonRateThrottle
from rest_framework import permissions, serializers, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response

from apps.insights import pagespeed_jobs
from apps.insights.analyzers import (
    PublicHostError,
    analyze_email,
    analyze_quick_scan,
    analyze_speed,
    score_url_risk,
)


class InsightsAnonThrottle(AnonRateThrottle):
    """免登入 insights 端點的專屬 throttle，用 rate 表中的 `insights` scope。"""

    scope = "insights"


class InsightsPollThrottle(AnonRateThrottle):
    """測速結果輪詢用；每次輪詢都算一次，額度另計，不吃掉 `insights` 的 30 次。"""

    scope = "insights_poll"


class SpeedAnalysisSerializer(serializers.Serializer):
    url = serializers.CharField(max_length=2048)
    authorization_confirmed = serializers.BooleanField()

    def validate_authorization_confirmed(self, value):
        if not value:
            raise serializers.ValidationError("請確認你擁有分析授權或該頁面可公開測速。")
        return value


class UrlRiskSerializer(serializers.Serializer):
    url = serializers.CharField(max_length=2048)


class EmailRiskSerializer(serializers.Serializer):
    raw_email = serializers.CharField(max_length=200_000)


class QuickScanSerializer(serializers.Serializer):
    url = serializers.CharField(max_length=2048)
    authorization_confirmed = serializers.BooleanField()

    def validate_authorization_confirmed(self, value):
        if not value:
            raise serializers.ValidationError("請確認你擁有分析授權或該頁面可公開檢測。")
        return value


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
@throttle_classes([InsightsAnonThrottle])
def speed_test(request):
    serializer = SpeedAnalysisSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        result = analyze_speed(serializer.validated_data["url"])
    except PublicHostError as exc:
        return Response({"url": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except ValueError as exc:
        return Response({"url": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        return Response(
            {"detail": "測速失敗，請稍後再試或確認該網址可公開連線。"},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    result["pagespeed"] = pagespeed_jobs.start(result.get("final_url") or result["url"])
    if result["pagespeed"]["status"] != "unavailable":
        result["core_web_vitals_note"] = (
            "上方是 Argus 單次輕量量測（伺服器回應與 HTML）；下方的 Google PageSpeed Insights "
            "提供 Lighthouse 分數與 Chrome 真實使用者資料（CrUX）。"
        )
    return Response(result)


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
@throttle_classes([InsightsPollThrottle])
def speed_test_pagespeed(request, job_id):
    """輪詢測速的 Google PageSpeed Insights 結果：pending／done／failed；代號不存在或過期回 404。"""
    payload = pagespeed_jobs.get(job_id)
    if payload is None:
        return Response({"detail": "量測已過期，請重新測速。"}, status=status.HTTP_404_NOT_FOUND)
    return Response(payload)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
@throttle_classes([InsightsAnonThrottle])
def phishing_url_check(request):
    serializer = UrlRiskSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        result = score_url_risk(serializer.validated_data["url"])
    except ValueError as exc:
        return Response({"url": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(result)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
@throttle_classes([InsightsAnonThrottle])
def phishing_email_check(request):
    serializer = EmailRiskSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    result = analyze_email(serializer.validated_data["raw_email"])
    return Response(result)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
@throttle_classes([InsightsAnonThrottle])
def quick_scan(request):
    """免登入單頁健檢（試用版）：HTTP 抓單頁 + 輕量四維檢查，不啟 Playwright、不扣 coin。"""
    serializer = QuickScanSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        result = analyze_quick_scan(serializer.validated_data["url"])
    except PublicHostError as exc:
        return Response({"url": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except ValueError as exc:
        return Response({"url": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        return Response(
            {"detail": "單頁健檢失敗，請稍後再試或確認該網址可公開連線。"},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    return Response(result)

